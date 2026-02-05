import os
import traceback
from datetime import datetime

from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity
from biz.event.event_manager import event_manager
from biz.platforms.gitlab.webhook_handler import (
    filter_changes,
    MergeRequestHandler,
    PushHandler,
)
from biz.platforms.github.webhook_handler import (
    filter_changes as filter_github_changes,
    PullRequestHandler as GithubPullRequestHandler,
    PushHandler as GithubPushHandler,
)
from biz.platforms.gitea.webhook_handler import (
    filter_changes as filter_gitea_changes,
    PullRequestHandler as GiteaPullRequestHandler,
    PushHandler as GiteaPushHandler,
)
from biz.service.review_service import ReviewService
from biz.llm.config import get_llm_value
from biz.utils.code_reviewer import CodeReviewer
from biz.llm.factory import LLMRetryExhaustedError
from biz.utils.im import notifier
from biz.utils.log import logger


def get_model_name():
    """获取当前使用的AI模型名称，从.env中的xxx_API_MODEL字段读取"""
    provider = get_llm_value("LLM_PROVIDER", "unknown")

    # 映射provider到对应的环境变量名
    api_model_env_map = {
        "anthropic": "ANTHROPIC_API_MODEL",
        "zhipuai": "ZHIPUAI_API_MODEL",
        "openai": "OPENAI_API_MODEL",
        "deepseek": "DEEPSEEK_API_MODEL",
        "ollama": "OLLAMA_API_MODEL",
        "qwen": "QWEN_API_MODEL",
    }

    # 获取对应的环境变量名，并读取模型名称
    env_var_name = api_model_env_map.get(provider)
    if env_var_name:
        model_name = get_llm_value(env_var_name)
        if model_name:
            return model_name

    # 如果找不到具体模型名，返回provider的友好名称
    provider_friendly_names = {
        "anthropic": "Claude",
        "zhipuai": "智谱AI",
        "openai": "GPT",
        "deepseek": "DeepSeek",
        "ollama": "Ollama",
        "qwen": "通义千问",
    }
    return provider_friendly_names.get(provider, provider.upper())


def handle_push_event(
    webhook_data: dict,
    gitlab_token: str,
    gitlab_url: str,
    gitlab_url_slug: str,
    record_id: int = None,
):
    push_review_enabled = os.environ.get("PUSH_REVIEW_ENABLED", "0") == "1"
    try:
        handler = PushHandler(webhook_data, gitlab_token, gitlab_url)
        logger.info("Push Hook event received")
        commits = handler.get_push_commits()
        if not commits:
            logger.error("Failed to get commits")
            if record_id is not None:
                ReviewService.update_push_review_log(
                    record_id=record_id,
                    score=0,
                    review_result="Failed to get commits",
                    status="failed",
                    language=language,
                )
            return

        review_result = None
        score = 0
        additions = 0
        deletions = 0
        language = ""
        author_display_name = webhook_data.get("user_name") or webhook_data.get(
            "user_username"
        )
        if push_review_enabled:
            # 获取PUSH的changes
            changes = handler.get_push_changes()
            logger.info("changes: %s", changes)
            changes = filter_changes(changes)
            if not changes:
                logger.info(
                    "未检测到PUSH代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。"
                )
            review_result = "关注的文件没有修改"

            language = CodeReviewer.detect_primary_language_name(changes)

            if len(changes) > 0:
                commits_text = ";".join(
                    commit.get("message", "").strip() for commit in commits
                )
                try:
                    review_result = CodeReviewer(changes=changes).review_and_strip_code(
                        str(changes), commits_text, changes=changes
                    )
                    score = CodeReviewer.parse_review_score(review_text=review_result)
                    for item in changes:
                        additions += item["additions"]
                        deletions += item["deletions"]
                    # 提交审查结果到 GitLab
                    handler.add_push_notes(review_result)
                except LLMRetryExhaustedError as e:
                    logger.error(
                        f"❌ AI 审查失败，跳过提交评论。Commit: {commits[-1].get('id', 'unknown') if commits else 'unknown'}, 错误: {e}"
                    )
                    review_result = f"AI 审查失败（{get_model_name()}）：{str(e)[:100]}"
                    score = 0
                    # 发送失败事件，status='failed'
                    if record_id is not None:
                        ReviewService.update_push_review_log(
                            record_id=record_id,
                            score=0,
                            review_result=review_result,
                            status="failed",
                            language=language,
                        )
                        return

                    event_manager["push_reviewed"].send(
                        PushReviewEntity(
                            project_name=webhook_data["project"]["name"],
                            author=webhook_data["user_username"],
                            author_display_name=author_display_name,
                            branch=webhook_data.get("ref", "").replace(
                                "refs/heads/", ""
                            ),
                            updated_at=int(datetime.now().timestamp()),
                            commits=commits,
                            score=score,
                            review_result=review_result,
                            language=language,
                            url_slug=gitlab_url_slug,
                            webhook_data=webhook_data,
                            additions=additions,
                            deletions=deletions,
                        ),
                        status="failed",
                    )
                    return

        if record_id is not None:
            ReviewService.update_push_review_log(
                record_id=record_id,
                score=score,
                review_result=review_result or "",
                status="success",
                language=language,
            )
            return

        event_manager["push_reviewed"].send(
            PushReviewEntity(
                project_name=webhook_data["project"]["name"],
                author=webhook_data["user_username"],
                author_display_name=author_display_name,
                branch=webhook_data.get("ref", "").replace("refs/heads/", ""),
                updated_at=int(datetime.now().timestamp()),  # 当前时间
                commits=commits,
                score=score,
                review_result=review_result,
                language=language if push_review_enabled else "",
                url_slug=gitlab_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
            ),
            status="success",
        )

    except Exception as e:
        error_message = f"服务出现未知错误: {str(e)}\n{traceback.format_exc()}"
        notifier.send_notification(content=error_message)
        logger.error("出现未知错误: %s", error_message)


def handle_merge_request_event(
    webhook_data: dict,
    gitlab_token: str,
    gitlab_url: str,
    gitlab_url_slug: str,
    record_id: int = None,
):
    """
    处理Merge Request Hook事件
    :param webhook_data:
    :param gitlab_token:
    :param gitlab_url:
    :param gitlab_url_slug:
    :return:
    """
    merge_review_only_protected_branches = (
        os.environ.get("MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED", "0") == "1"
    )
    try:
        # 解析Webhook数据
        handler = MergeRequestHandler(webhook_data, gitlab_token, gitlab_url)
        logger.info("Merge Request Hook event received")

        # 新增：判断是否为draft（草稿）MR
        object_attributes = webhook_data.get("object_attributes", {})
        is_draft = object_attributes.get("draft") or object_attributes.get(
            "work_in_progress"
        )
        if is_draft:
            msg = f"[通知] MR为草稿（draft），未触发AI审查。\n项目: {webhook_data['project']['name']}\n作者: {webhook_data['user']['username']}\n源分支: {object_attributes.get('source_branch')}\n目标分支: {object_attributes.get('target_branch')}\n链接: {object_attributes.get('url')}"
            notifier.send_notification(content=msg)
            logger.info("MR为draft，仅发送通知，不触发AI review。")
            return

        # 如果开启了仅review projected branches的，判断当前目标分支是否为projected branches
        if (
            merge_review_only_protected_branches
            and not handler.target_branch_protected()
        ):
            logger.info(
                "Merge Request target branch not match protected branches, ignored."
            )
            return

        if handler.action not in ["open", "update"]:
            logger.info(f"Merge Request Hook event, action={handler.action}, ignored.")
            return

        # 检查last_commit_id是否已经存在，如果存在则跳过处理
        last_commit_id = object_attributes.get("last_commit", {}).get("id", "")
        if last_commit_id:
            project_name = webhook_data["project"]["name"]
            source_branch = object_attributes.get("source_branch", "")
            target_branch = object_attributes.get("target_branch", "")

            if ReviewService.check_mr_last_commit_id_exists(
                project_name, source_branch, target_branch, last_commit_id
            ):
                logger.info(
                    f"Merge Request with last_commit_id {last_commit_id} already exists, skipping review for {project_name}."
                )
                return

        # 仅仅在MR创建或更新时进行Code Review
        # 获取Merge Request的changes
        changes = handler.get_merge_request_changes()
        logger.info("changes: %s", changes)
        changes = filter_changes(changes)
        if not changes:
            logger.info(
                "未检测到有关代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。"
            )
            return

        language = CodeReviewer.detect_primary_language_name(changes)
        # 统计本次新增、删除的代码总数
        additions = 0
        deletions = 0
        for item in changes:
            additions += item.get("additions", 0)
            deletions += item.get("deletions", 0)

        # 获取Merge Request的commits
        commits = handler.get_merge_request_commits()
        if not commits:
            logger.error("Failed to get commits")
            if record_id is not None:
                ReviewService.update_mr_review_log(
                    record_id=record_id,
                    score=0,
                    review_result="Failed to get commits",
                    status="failed",
                    language=language,
                )
            return

        # review 代码
        commits_text = ";".join(commit["title"] for commit in commits)
        try:
            review_result = CodeReviewer(changes=changes).review_and_strip_code(
                str(changes), commits_text, changes=changes
            )

            # 将review结果提交到Gitlab的 notes
            handler.add_merge_request_notes(review_result)
        except LLMRetryExhaustedError as e:
            logger.error(
                f"❌ AI 审查失败，跳过提交评论。MR: {handler.merge_request_iid}, 错误: {e}"
            )
            review_result = f"AI 审查失败（{get_model_name()}）：{str(e)[:100]}"
            score = 0
            author_info = webhook_data.get("user", {})
            author_display_name = author_info.get("name") or author_info.get("username")
            if record_id is not None:
                ReviewService.update_mr_review_log(
                    record_id=record_id,
                    score=0,
                    review_result=review_result,
                    status="failed",
                    language=language,
                )
                return

            event_manager["merge_request_reviewed"].send(
                MergeRequestReviewEntity(
                    project_name=webhook_data["project"]["name"],
                    author=webhook_data["user"]["username"],
                    author_display_name=author_display_name,
                    source_branch=webhook_data["object_attributes"]["source_branch"],
                    target_branch=webhook_data["object_attributes"]["target_branch"],
                    updated_at=int(datetime.now().timestamp()),
                    commits=commits,
                    score=score,
                    url=webhook_data["object_attributes"]["url"],
                    review_result=review_result,
                    language=language,
                    url_slug=gitlab_url_slug,
                    webhook_data=webhook_data,
                    additions=additions,
                    deletions=deletions,
                    last_commit_id=last_commit_id,
                ),
                status="failed",
            )
            return

        author_info = webhook_data.get("user", {})
        author_display_name = author_info.get("name") or author_info.get("username")
        if record_id is not None:
            ReviewService.update_mr_review_log(
                record_id=record_id,
                score=CodeReviewer.parse_review_score(review_text=review_result),
                review_result=review_result,
                status="success",
                language=language,
            )
            return

        event_manager["merge_request_reviewed"].send(
            MergeRequestReviewEntity(
                project_name=webhook_data["project"]["name"],
                author=webhook_data["user"]["username"],
                author_display_name=author_display_name,
                source_branch=webhook_data["object_attributes"]["source_branch"],
                target_branch=webhook_data["object_attributes"]["target_branch"],
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=CodeReviewer.parse_review_score(review_text=review_result),
                url=webhook_data["object_attributes"]["url"],
                review_result=review_result,
                language=language,
                url_slug=gitlab_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
                last_commit_id=last_commit_id,
            ),
            status="success",
        )

    except Exception as e:
        error_message = (
            f"AI Code Review 服务出现未知错误: {str(e)}\n{traceback.format_exc()}"
        )
        notifier.send_notification(content=error_message)
        logger.error("出现未知错误: %s", error_message)


def handle_github_push_event(
    webhook_data: dict, github_token: str, github_url: str, github_url_slug: str
):
    push_review_enabled = os.environ.get("PUSH_REVIEW_ENABLED", "0") == "1"
    try:
        handler = GithubPushHandler(webhook_data, github_token, github_url)
        logger.info("GitHub Push event received")
        commits = handler.get_push_commits()
        if not commits:
            logger.error("Failed to get commits")
            return

        review_result = None
        score = 0
        additions = 0
        deletions = 0
        language = ""
        sender = webhook_data.get("sender", {})
        pusher = webhook_data.get("pusher", {})
        head_commit = webhook_data.get("head_commit", {}) or {}
        head_commit_author = (
            head_commit.get("author", {}) if isinstance(head_commit, dict) else {}
        )
        author_display_name = (
            pusher.get("name") or head_commit_author.get("name") or sender.get("login")
        )
        if push_review_enabled:
            # 获取PUSH的changes
            changes = handler.get_push_changes()
            logger.info("changes: %s", changes)
            changes = filter_github_changes(changes)
            language = CodeReviewer.detect_primary_language_name(changes)
            if not changes:
                logger.info(
                    "未检测到PUSH代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。"
                )
            review_result = "关注的文件没有修改"

            if len(changes) > 0:
                commits_text = ";".join(
                    commit.get("message", "").strip() for commit in commits
                )
                try:
                    review_result = CodeReviewer(changes=changes).review_and_strip_code(
                        str(changes), commits_text, changes=changes
                    )
                    score = CodeReviewer.parse_review_score(review_text=review_result)
                    for item in changes:
                        additions += item.get("additions", 0)
                        deletions += item.get("deletions", 0)
                    handler.add_push_notes(review_result)
                except LLMRetryExhaustedError as e:
                    logger.error(
                        f"❌ AI 审查失败，跳过提交评论。Commit: {commits[-1].get('id', 'unknown') if commits else 'unknown'}, 错误: {e}"
                    )
                    review_result = f"AI 审查失败（{get_model_name()}）：{str(e)[:100]}"
                    score = 0
                    event_manager["push_reviewed"].send(
                        PushReviewEntity(
                            project_name=webhook_data["repository"]["name"],
                            author=webhook_data["sender"]["login"],
                            author_display_name=author_display_name,
                            branch=webhook_data["ref"].replace("refs/heads/", ""),
                            updated_at=int(datetime.now().timestamp()),
                            commits=commits,
                            score=score,
                            review_result=review_result,
                            language=language,
                            url_slug=github_url_slug,
                            webhook_data=webhook_data,
                            additions=additions,
                            deletions=deletions,
                        ),
                        status="failed",
                    )
                    return

        event_manager["push_reviewed"].send(
            PushReviewEntity(
                project_name=webhook_data["repository"]["name"],
                author=webhook_data["sender"]["login"],
                author_display_name=author_display_name,
                branch=webhook_data["ref"].replace("refs/heads/", ""),
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=score,
                review_result=review_result,
                language=language if push_review_enabled else "",
                url_slug=github_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
            ),
            status="success",
        )

    except Exception as e:
        error_message = f"服务出现未知错误: {str(e)}\n{traceback.format_exc()}"
        notifier.send_notification(content=error_message)
        logger.error("出现未知错误: %s", error_message)


def handle_github_pull_request_event(
    webhook_data: dict, github_token: str, github_url: str, github_url_slug: str
):
    """
    处理GitHub Pull Request 事件
    :param webhook_data:
    :param github_token:
    :param github_url:
    :param github_url_slug:
    :return:
    """
    merge_review_only_protected_branches = (
        os.environ.get("MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED", "0") == "1"
    )
    try:
        # 解析Webhook数据
        handler = GithubPullRequestHandler(webhook_data, github_token, github_url)
        logger.info("GitHub Pull Request event received")
        # 如果开启了仅review projected branches的，判断当前目标分支是否为projected branches
        if (
            merge_review_only_protected_branches
            and not handler.target_branch_protected()
        ):
            logger.info(
                "Merge Request target branch not match protected branches, ignored."
            )
            return

        if handler.action not in ["opened", "synchronize"]:
            logger.info(f"Pull Request Hook event, action={handler.action}, ignored.")
            return

        # 检查GitHub Pull Request的last_commit_id是否已经存在，如果存在则跳过处理
        github_last_commit_id = webhook_data["pull_request"]["head"]["sha"]
        if github_last_commit_id:
            project_name = webhook_data["repository"]["name"]
            source_branch = webhook_data["pull_request"]["head"]["ref"]
            target_branch = webhook_data["pull_request"]["base"]["ref"]

            if ReviewService.check_mr_last_commit_id_exists(
                project_name, source_branch, target_branch, github_last_commit_id
            ):
                logger.info(
                    f"Pull Request with last_commit_id {github_last_commit_id} already exists, skipping review for {project_name}."
                )
                return

        # 仅仅在PR创建或更新时进行Code Review
        # 获取Pull Request的changes
        changes = handler.get_pull_request_changes()
        logger.info("changes: %s", changes)
        changes = filter_github_changes(changes)
        if not changes:
            logger.info(
                "未检测到有关代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。"
            )
            return

        language = CodeReviewer.detect_primary_language_name(changes)
        # 统计本次新增、删除的代码总数
        additions = 0
        deletions = 0
        for item in changes:
            additions += item.get("additions", 0)
            deletions += item.get("deletions", 0)

        # 获取Pull Request的commits
        commits = handler.get_pull_request_commits()
        if not commits:
            logger.error("Failed to get commits")
            return

        # review 代码
        commits_text = ";".join(commit["title"] for commit in commits)
        try:
            review_result = CodeReviewer(changes=changes).review_and_strip_code(
                str(changes), commits_text, changes=changes
            )
            handler.add_pull_request_notes(review_result)
        except LLMRetryExhaustedError as e:
            logger.error(
                f"❌ AI 审查失败，跳过提交评论。PR: {handler.pull_request_number}, 错误: {e}"
            )
            review_result = f"AI 审查失败（{get_model_name()}）：{str(e)[:100]}"
            score = 0
            author_info = (
                webhook_data.get("pull_request", {}).get("user", {})
                or webhook_data.get("sender", {})
                or {}
            )
            author_display_name = author_info.get("name") or author_info.get("login")
            event_manager["merge_request_reviewed"].send(
                MergeRequestReviewEntity(
                    project_name=webhook_data["repository"]["name"],
                    author=webhook_data["pull_request"]["user"]["login"],
                    author_display_name=author_display_name,
                    source_branch=webhook_data["pull_request"]["head"]["ref"],
                    target_branch=webhook_data["pull_request"]["base"]["ref"],
                    updated_at=int(datetime.now().timestamp()),
                    commits=commits,
                    score=score,
                    url=webhook_data["pull_request"]["html_url"],
                    review_result=review_result,
                    language=language,
                    url_slug=github_url_slug,
                    webhook_data=webhook_data,
                    additions=additions,
                    deletions=deletions,
                    last_commit_id=github_last_commit_id,
                ),
                status="failed",
            )
            return

        author_info = (
            webhook_data.get("pull_request", {}).get("user", {})
            or webhook_data.get("sender", {})
            or {}
        )
        author_display_name = author_info.get("name") or author_info.get("login")
        event_manager["merge_request_reviewed"].send(
            MergeRequestReviewEntity(
                project_name=webhook_data["repository"]["name"],
                author=webhook_data["pull_request"]["user"]["login"],
                author_display_name=author_display_name,
                source_branch=webhook_data["pull_request"]["head"]["ref"],
                target_branch=webhook_data["pull_request"]["base"]["ref"],
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=CodeReviewer.parse_review_score(review_text=review_result),
                url=webhook_data["pull_request"]["html_url"],
                review_result=review_result,
                language=language,
                url_slug=github_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
                last_commit_id=github_last_commit_id,
            ),
            status="success",
        )

    except Exception as e:
        error_message = f"服务出现未知错误: {str(e)}\n{traceback.format_exc()}"
        notifier.send_notification(content=error_message)
        logger.error("出现未知错误: %s", error_message)


def handle_gitea_push_event(
    webhook_data: dict, gitea_token: str, gitea_url: str, gitea_url_slug: str
):
    push_review_enabled = os.environ.get("PUSH_REVIEW_ENABLED", "0") == "1"
    try:
        handler = GiteaPushHandler(webhook_data, gitea_token, gitea_url)
        logger.info("Gitea Push event received")
        commits = handler.get_push_commits()
        if not commits:
            logger.error("Failed to get commits")
            return

        review_result = None
        score = 0
        additions = 0
        deletions = 0
        language = ""
        repository = webhook_data.get("repository", {})
        sender = webhook_data.get("sender", {}) or webhook_data.get("pusher", {}) or {}
        author_display_name = (
            sender.get("full_name")
            or sender.get("name")
            or sender.get("login")
            or sender.get("username")
        )
        if push_review_enabled:
            changes = handler.get_push_changes()
            logger.info("changes: %s", changes)
            changes = filter_gitea_changes(changes)
            language = CodeReviewer.detect_primary_language_name(changes)
            if not changes:
                logger.info(
                    "未检测到PUSH代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。"
                )
            review_result = "关注的文件没有修改"

            if len(changes) > 0:
                commits_text = ";".join(
                    commit.get("message", "").strip() for commit in commits
                )
                try:
                    review_result = CodeReviewer(changes=changes).review_and_strip_code(
                        str(changes), commits_text, changes=changes
                    )
                    score = CodeReviewer.parse_review_score(review_text=review_result)
                    for item in changes:
                        additions += item.get("additions", 0)
                        deletions += item.get("deletions", 0)
                    handler.add_push_notes(review_result)
                except LLMRetryExhaustedError as e:
                    logger.error(
                        f"❌ AI 审查失败，跳过提交评论。Commit: {commits[-1].get('id', 'unknown') if commits else 'unknown'}, 错误: {e}"
                    )
                    review_result = f"AI 审查失败（{get_model_name()}）：{str(e)[:100]}"
                    score = 0
                    event_manager["push_reviewed"].send(
                        PushReviewEntity(
                            project_name=repository.get("name"),
                            author=sender.get("login") or sender.get("username"),
                            author_display_name=author_display_name,
                            branch=handler.branch_name,
                            updated_at=int(datetime.now().timestamp()),
                            commits=commits,
                            score=score,
                            review_result=review_result,
                            language=language,
                            url_slug=gitea_url_slug,
                            webhook_data=webhook_data,
                            additions=additions,
                            deletions=deletions,
                        ),
                        status="failed",
                    )
                    return

        event_manager["push_reviewed"].send(
            PushReviewEntity(
                project_name=repository.get("name"),
                author=sender.get("login") or sender.get("username"),
                author_display_name=author_display_name,
                branch=handler.branch_name,
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=score,
                review_result=review_result,
                language=language if push_review_enabled else "",
                url_slug=gitea_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
            ),
            status="success",
        )

    except Exception as e:
        error_message = f"服务出现未知错误: {str(e)}\n{traceback.format_exc()}"
        notifier.send_notification(content=error_message)
        logger.error("出现未知错误: %s", error_message)


def handle_gitea_pull_request_event(
    webhook_data: dict, gitea_token: str, gitea_url: str, gitea_url_slug: str
):
    merge_review_only_protected_branches = (
        os.environ.get("MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED", "0") == "1"
    )
    try:
        handler = GiteaPullRequestHandler(webhook_data, gitea_token, gitea_url)
        logger.info("Gitea Pull Request event received")

        pull_request = webhook_data.get("pull_request", {})

        if (
            merge_review_only_protected_branches
            and not handler.target_branch_protected()
        ):
            logger.info(
                "Pull Request target branch not match protected branches, ignored."
            )
            return

        if handler.action not in [
            "opened",
            "open",
            "reopened",
            "synchronize",
            "synchronized",
        ]:
            logger.info(f"Pull Request Hook event, action={handler.action}, ignored.")
            return

        head_info = pull_request.get("head") or {}
        base_info = pull_request.get("base") or {}

        last_commit_id = (
            head_info.get("sha")
            or pull_request.get("merge_commit_sha")
            or pull_request.get("last_commit_id")
        )
        if last_commit_id:
            project_name = webhook_data.get("repository", {}).get("name")
            source_branch = head_info.get("ref") or pull_request.get("head_branch", "")
            target_branch = base_info.get("ref") or pull_request.get("base_branch", "")

            if ReviewService.check_mr_last_commit_id_exists(
                project_name, source_branch, target_branch, last_commit_id
            ):
                logger.info(
                    f"Pull Request with last_commit_id {last_commit_id} already exists, skipping review for {project_name}."
                )
                return

        changes = handler.get_pull_request_changes()
        logger.info("changes: %s", changes)
        changes = filter_gitea_changes(changes)
        if not changes:
            logger.info(
                "未检测到有关代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。"
            )
            return

        language = CodeReviewer.detect_primary_language_name(changes)

        additions = 0
        deletions = 0
        for item in changes:
            additions += item.get("additions", 0)
            deletions += item.get("deletions", 0)

        commits = handler.get_pull_request_commits()
        if not commits:
            logger.error("Failed to get commits for Gitea pull request")
            return

        commits_text = ";".join(commit.get("title", "") for commit in commits)
        try:
            review_result = CodeReviewer(changes=changes).review_and_strip_code(
                str(changes), commits_text, changes=changes
            )
            handler.add_pull_request_notes(review_result)
        except LLMRetryExhaustedError as e:
            logger.error(
                f"❌ AI 审查失败，跳过提交评论。PR: {handler.pull_request_index}, 错误: {e}"
            )
            review_result = f"AI 审查失败（{get_model_name()}）：{str(e)[:100]}"
            score = 0
            repository = webhook_data.get("repository", {})
            author_info = (
                pull_request.get("user", {}) or webhook_data.get("sender", {}) or {}
            )
            author_display_name = (
                author_info.get("full_name")
                or author_info.get("name")
                or author_info.get("login")
                or author_info.get("username")
            )
            event_manager["merge_request_reviewed"].send(
                MergeRequestReviewEntity(
                    project_name=repository.get("name"),
                    author=author_info.get("login") or author_info.get("username"),
                    author_display_name=author_display_name,
                    source_branch=head_info.get("ref")
                    or pull_request.get("head_branch", ""),
                    target_branch=base_info.get("ref")
                    or pull_request.get("base_branch", ""),
                    updated_at=int(datetime.now().timestamp()),
                    commits=commits,
                    score=score,
                    url=pull_request.get("html_url") or pull_request.get("url"),
                    review_result=review_result,
                    language=language,
                    url_slug=gitea_url_slug,
                    webhook_data=webhook_data,
                    additions=additions,
                    deletions=deletions,
                    last_commit_id=last_commit_id,
                ),
                status="failed",
            )
            return

        repository = webhook_data.get("repository", {})
        author_info = (
            pull_request.get("user", {}) or webhook_data.get("sender", {}) or {}
        )
        author_display_name = (
            author_info.get("full_name")
            or author_info.get("name")
            or author_info.get("login")
            or author_info.get("username")
        )

        event_manager["merge_request_reviewed"].send(
            MergeRequestReviewEntity(
                project_name=repository.get("name"),
                author=author_info.get("login") or author_info.get("username"),
                author_display_name=author_display_name,
                source_branch=head_info.get("ref")
                or pull_request.get("head_branch", ""),
                target_branch=base_info.get("ref")
                or pull_request.get("base_branch", ""),
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=CodeReviewer.parse_review_score(review_text=review_result),
                url=pull_request.get("html_url") or pull_request.get("url"),
                review_result=review_result,
                language=language,
                url_slug=gitea_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
                last_commit_id=last_commit_id,
            ),
            status="success",
        )

    except Exception as e:
        error_message = (
            f"AI Code Review 服务出现未知错误: {str(e)}\n{traceback.format_exc()}"
        )
        notifier.send_notification(content=error_message)
        logger.error("出现未知错误: %s", error_message)
