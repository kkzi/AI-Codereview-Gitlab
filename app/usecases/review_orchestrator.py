"""审查编排器 - 统一的代码审查流程"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import AppConfig
from app.core.logging import get_logger
from app.core.token_util import count_tokens, truncate_text_by_tokens
from app.infra.db.sqlite import SQLiteRepository
from app.infra.llm.factory import LLMRetryExhaustedError, get_client, get_model_name
from app.infra.notify.notifier import send_notification
from app.usecases.platform_handler import PlatformHandler
from app.usecases.prompt_builder import PromptBuilder, parse_review_score

logger = get_logger(__name__)


class ReviewOrchestrator:
    """代码审查编排器 - 处理通用的审查流程"""

    def __init__(
        self,
        repo: SQLiteRepository,
        config: AppConfig,
        handler: PlatformHandler,
    ):
        self.repo = repo
        self.config = config
        self.handler = handler
        self.llm_client = get_client()
        self.model_name = get_model_name()
        self.prompt_builder = PromptBuilder(self.config.review_style, self.model_name)

    def process_merge_request(
        self,
        payload: Dict[str, Any],
        event_id: Optional[int] = None,
        record_id: Optional[int] = None,
    ) -> None:
        """处理MR/PR审查"""
        logger.info("Processing merge request: event_id=%s", event_id)

        # 解析MR信息
        mr_info = self.handler.parse_merge_request_info(payload)
        if not mr_info:
            logger.warning("Failed to parse merge request info")
            return

        # 检查是否为草稿
        if mr_info["is_draft"]:
            self._notify_draft_mr(mr_info, payload)
            self._mark_skipped("mr", record_id, "MR 为 draft")
            return

        # 检查目标分支保护
        if self.config.merge_review_only_protected_branches_enabled:
            if not self.handler.is_target_branch_protected(
                mr_info["project_id"], mr_info["target_branch"]
            ):
                self._mark_skipped("mr", record_id, "目标分支非受保护分支")
                return

        # 检查action
        allowed_actions = {"open", "update", "opened", "synchronize", "reopened", "synchronized"}
        if mr_info["action"] and mr_info["action"] not in allowed_actions:
            self._mark_skipped("mr", record_id, f"action={mr_info['action']} 非允许范围")
            return

        # 检查last_commit_id是否已存在
        if mr_info["last_commit_id"] and self.repo.check_mr_last_commit_id_exists(
            mr_info["project_name"],
            mr_info["source_branch"],
            mr_info["target_branch"],
            mr_info["last_commit_id"],
        ):
            self._mark_skipped(
                "mr", record_id, f"last_commit_id={mr_info['last_commit_id']} 已存在"
            )
            return

        # 获取变更和提交
        changes = self.handler.get_merge_request_changes(
            mr_info["project_id"], mr_info["mr_number"]
        )
        filtered = self.handler.filter_changes(changes)
        if not filtered:
            self._mark_skipped("mr", record_id, "未检测到有效变更或文件类型不支持")
            return

        commits = self.handler.get_merge_request_commits(
            mr_info["project_id"], mr_info["mr_number"]
        )
        if not commits:
            self._mark_skipped("mr", record_id, "未获取到提交记录")
            return

        # 执行审查
        review_text, score, language, status = self._review_changes(
            filtered, commits, "未检测到有效变更或文件类型不支持"
        )

        if status == "failed" and record_id is not None:
            return

        # 发布评论
        if status == "success":
            self.handler.add_merge_request_comment(
                mr_info["project_id"], mr_info["mr_number"], review_text
            )

        # 保存结果
        if record_id:
            self.repo.update_mr_review_log(
                record_id=int(record_id),
                score=score,
                review_result=review_text,
                status=status,
                language=language,
                model_name=self.model_name or "",
            )
        else:
            self.repo.insert_mr_review_log(
                project_name=mr_info["project_name"],
                author=mr_info["author"],
                author_display_name=mr_info["author_display_name"],
                source_branch=mr_info["source_branch"],
                target_branch=mr_info["target_branch"],
                updated_at=int(time.time()),
                commit_messages=self._join_commit_messages(commits),
                score=score,
                model_name=self.model_name,
                language=language,
                url=mr_info["url"],
                review_result=review_text,
                additions=self._sum_changes(filtered)[0],
                deletions=self._sum_changes(filtered)[1],
                last_commit_id=mr_info["last_commit_id"],
                status=status,
                project_url=mr_info["project_url"],
                commit_url=mr_info["url"],
                event_id=event_id,
            )

        # 发送通知
        if status == "success":
            self._notify_merge_request(mr_info, commits, review_text, payload)

        logger.info(
            "MR review completed: total=%s, filtered=%s, commits=%s",
            len(changes),
            len(filtered),
            len(commits),
        )

    def process_push(
        self,
        payload: Dict[str, Any],
        event_id: Optional[int] = None,
        record_id: Optional[int] = None,
    ) -> None:
        """处理Push审查"""
        logger.info("Processing push: event_id=%s", event_id)

        # 解析Push信息
        push_info = self.handler.parse_push_info(payload)
        if not push_info:
            logger.warning("Failed to parse push info")
            return

        # 获取提交记录
        commits = self.handler.get_push_commits(payload)
        if not commits:
            self._mark_skipped("push", record_id, "未获取到提交记录")
            return

        # 检查是否启用Push审查
        if not self.config.push_review_enabled:
            review_text = "AI 审查未启用"
            score = 0
            language = ""
            status = "skipped" if record_id is not None else "success"
            filtered = []
        else:
            # 获取变更
            changes = self.handler.get_push_changes(push_info["project_id"], payload)
            filtered = self.handler.filter_changes(changes)

            if not filtered:
                fallback_paths = self._extract_supported_paths_from_payload(payload)
                if fallback_paths:
                    hint = ", ".join(fallback_paths[:5])
                    if len(fallback_paths) > 5:
                        hint = f"{hint} 等 {len(fallback_paths)} 个文件"
                    reason = (
                        "检测到文件变更，但无法获取 diff（请检查 Git 平台 API/Token/网络）；"
                        f"文件: {hint}"
                    )
                    logger.warning("Push diff unavailable: %s", hint)
                    if record_id is not None:
                        self._mark_skipped("push", record_id, reason)
                        return
                    review_text = f"跳过 AI 审查：{reason}"
                    score = 0
                    language = self.prompt_builder.detect_primary_language_name(
                        [{"new_path": path} for path in fallback_paths]
                    )
                    status = "skipped"
                else:
                    if record_id is not None:
                        self._mark_skipped("push", record_id, "未检测到有效变更或文件类型不支持")
                        return
                    review_text = "关注的文件没有修改"
                    score = 0
                    language = self.prompt_builder.detect_primary_language_name(filtered)
                    status = "success"
            else:
                # 执行审查
                review_text, score, language, status = self._review_changes(
                    filtered, commits, "关注的文件没有修改"
                )

        # 获取最后一个提交ID
        last_commit_id = push_info["after"] or (
            push_info["commit_list"][-1].get("id") if push_info["commit_list"] else ""
        )
        commit_url = commits[-1].get("url", "") if commits else ""

        # 发布评论
        if (
            status == "success"
            and last_commit_id
            and filtered
            and self.config.push_review_enabled
        ):
            self.handler.add_push_comment(
                push_info["project_id"], last_commit_id, review_text
            )

        if status == "failed" and record_id is not None:
            return

        # 保存结果
        if record_id:
            self.repo.update_push_review_log(
                record_id=int(record_id),
                score=score,
                review_result=review_text,
                status=status,
                language=language,
                model_name=self.model_name or "",
            )
        else:
            self.repo.insert_push_review_log(
                project_name=push_info["project_name"],
                author=push_info["author"],
                author_display_name=push_info["author_display_name"],
                branch=push_info["branch"],
                updated_at=int(time.time()),
                commit_messages=self._join_commit_messages(commits),
                score=score,
                model_name=self.model_name,
                language=language,
                review_result=review_text,
                additions=self._sum_changes(filtered)[0],
                deletions=self._sum_changes(filtered)[1],
                last_commit_id=last_commit_id or "",
                status=status,
                project_url=push_info["project_url"],
                commit_url=commit_url,
                event_id=event_id,
            )

        # 发送通知
        if status == "success":
            self._notify_push(push_info, commits, review_text, payload)

        logger.info(
            "Push review completed: filtered=%s, commits=%s",
            len(filtered),
            len(commits),
        )

    def _review_changes(
        self,
        changes: List[Dict],
        commits: List[Dict],
        empty_message: str,
    ) -> Tuple[str, int, str, str]:
        """执行代码审查"""
        language = self.prompt_builder.detect_primary_language_name(changes)
        if not changes:
            return empty_message, 0, language, "skipped"

        # Token截断
        changes_text = str(changes)
        if count_tokens(changes_text) > self.config.review_max_tokens:
            changes_text = truncate_text_by_tokens(
                changes_text, self.config.review_max_tokens
            )

        # 构建提示
        commits_text = self._join_commit_messages(commits)
        messages, language = self.prompt_builder.build_messages(
            changes_text, commits_text, changes
        )

        # 调用LLM
        try:
            review_text = self.llm_client.completions(messages=messages)
            status = "success"
        except LLMRetryExhaustedError as exc:
            review_text = f"AI 审查失败（{self.model_name}）：{str(exc)[:200]}"
            status = "failed"
        except Exception as exc:
            logger.exception("Unexpected error in LLM call")
            review_text = f"AI 审查异常：{type(exc).__name__}"
            status = "failed"

        # 处理结果
        review_text = self._strip_markdown_fences(review_text)
        score = parse_review_score(review_text)
        return review_text, score, language, status

    def _mark_skipped(
        self, review_type: str, record_id: Optional[int], reason: str
    ) -> None:
        """标记为跳过"""
        logger.info("[SKIP_LLM] %s %s", review_type, reason)
        if record_id is None:
            return

        message = f"跳过 AI 审查：{reason}"
        if review_type == "mr":
            self.repo.update_mr_review_log(
                record_id=int(record_id),
                score=0,
                review_result=message,
                status="skipped",
                language="",
                model_name=self.model_name or "",
            )
        elif review_type == "push":
            self.repo.update_push_review_log(
                record_id=int(record_id),
                score=0,
                review_result=message,
                status="skipped",
                language="",
                model_name=self.model_name or "",
            )

    def _notify_draft_mr(
        self, mr_info: Dict[str, Any], payload: Dict[str, Any]
    ) -> None:
        """通知草稿MR"""
        msg = (
            f"[通知] MR为草稿（draft），未触发AI审查。\n"
            f"项目: {mr_info['project_name']}\n"
            f"作者: {mr_info['author']}\n"
            f"源分支: {mr_info['source_branch']}\n"
            f"目标分支: {mr_info['target_branch']}\n"
            f"链接: {mr_info['url']}"
        )
        send_notification(
            content=msg,
            msg_type="text",
            title="Merge Request Review",
            project_name=mr_info["project_name"],
            url_slug=self.handler.get_url_slug(),
            webhook_data=payload,
        )

    def _notify_merge_request(
        self,
        mr_info: Dict[str, Any],
        commits: List[Dict],
        review_text: str,
        payload: Dict[str, Any],
    ) -> None:
        """发送MR通知"""
        im_msg = f"""
### 🔀 {mr_info['project_name']}: Merge Request

#### 合并请求信息:
- **提交者:** {mr_info['author_display_name']}

- **源分支**: {mr_info['source_branch']}
- **目标分支**: {mr_info['target_branch']}
- **更新时间**: {int(time.time())}
- **提交信息:** {self._join_commit_messages(commits)}

- [查看合并详情]({mr_info['url']})

- **AI Review 结果:**

{review_text}
"""
        send_notification(
            content=im_msg,
            msg_type="markdown",
            title="Merge Request Review",
            project_name=mr_info["project_name"],
            url_slug=self.handler.get_url_slug(),
            webhook_data=payload,
        )

    def _notify_push(
        self,
        push_info: Dict[str, Any],
        commits: List[Dict],
        review_text: str,
        payload: Dict[str, Any],
    ) -> None:
        """发送Push通知"""
        im_msg = f"### 🚀 {push_info['project_name']}: Push\n\n"
        im_msg += "#### 提交记录:\n"

        if commits:
            latest = commits[0]
            message = (latest.get("message") or "").strip()
            author = latest.get("author") or push_info["author_display_name"]
            timestamp = latest.get("timestamp", "")
            url = latest.get("url", "#")
            im_msg += (
                f"- **提交信息**: {message}\n"
                f"- **提交者**: {author}\n"
                f"- **时间**: {timestamp}\n"
                f"- [查看提交详情]({url})\n\n"
            )
            if len(commits) > 1:
                im_msg += f"- 和其它 {len(commits) - 1} 条提交记录\n\n"

        if review_text:
            im_msg += f"#### AI Review 结果: \n {review_text}\n\n"

        send_notification(
            content=im_msg,
            msg_type="markdown",
            title=f"{push_info['project_name']} Push Event",
            project_name=push_info["project_name"],
            url_slug=self.handler.get_url_slug(),
            webhook_data=payload,
        )

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """移除markdown代码块标记"""
        if not text:
            return text
        if text.startswith("```markdown") and text.endswith("```"):
            return text[11:-3].strip()
        if text.startswith("```") and text.endswith("```"):
            return text[3:-3].strip()
        return text

    @staticmethod
    def _sum_changes(changes: List[Dict]) -> Tuple[int, int]:
        """计算变更的增删行数"""
        additions = 0
        deletions = 0
        for item in changes or []:
            additions += int(item.get("additions", 0) or 0)
            deletions += int(item.get("deletions", 0) or 0)
        return additions, deletions

    @staticmethod
    def _join_commit_messages(commits: List[Dict]) -> str:
        """连接提交消息"""
        return ";".join((commit.get("message") or "").strip() for commit in commits)

    @staticmethod
    def _extract_supported_paths_from_payload(payload: Dict[str, Any]) -> List[str]:
        commits = payload.get("commits") or []
        if not commits:
            return []
        supported = [
            ext.strip().lower()
            for ext in os.getenv("SUPPORTED_EXTENSIONS", ".java,.py,.php").split(",")
            if ext.strip()
        ]
        if not supported:
            return []
        paths: List[str] = []
        for commit in commits:
            for key in ("added", "modified", "removed"):
                for path in commit.get(key) or []:
                    if path:
                        paths.append(path)
        if not paths:
            return []
        seen = set()
        filtered: List[str] = []
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            lower_path = path.lower()
            if any(lower_path.endswith(ext) for ext in supported):
                filtered.append(path)
        return filtered
