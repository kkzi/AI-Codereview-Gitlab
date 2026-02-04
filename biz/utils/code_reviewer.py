import abc
import os
import re
from typing import Dict, Any, List, Optional

import yaml
from jinja2 import Template

from biz.llm.factory import Factory
from biz.utils.log import logger
from biz.utils.token_util import count_tokens, truncate_text_by_tokens


# 文件扩展名到提示词文件的映射
EXTENSION_TO_PROMPT = {
    '.py': 'python_prompt',
    '.java': 'java_prompt',
    '.js': 'javascript_prompt',
    '.ts': 'javascript_prompt',
    '.jsx': 'javascript_prompt',
    '.tsx': 'javascript_prompt',
    '.go': 'golang_prompt',
    '.cpp': 'cpp_prompt',
    '.cc': 'cpp_prompt',
    '.cxx': 'cpp_prompt',
    '.hpp': 'cpp_prompt',
    '.h': 'cpp_prompt',
    '.php': 'php_prompt',
    '.sql': 'sql_prompt',
    '.rb': 'ruby_prompt',
}


class BaseReviewer(abc.ABC):
    """代码审查基类"""

    def __init__(self, prompt_key: str, language_file: Optional[str] = None):
        self.client = Factory().getClient()
        if language_file:
            self.prompts = self._load_prompts_by_language(prompt_key, 
                                                          os.getenv("REVIEW_STYLE", "professional"),
                                                          language_file)
        else:
            self.prompts = self._load_prompts_by_language(prompt_key, 
                                                          os.getenv("REVIEW_STYLE", "professional"),
                                                          None)

    def _load_prompts(self, prompt_key: str, style="professional") -> Dict[str, Any]:
        """
        已废弃：请使用 _load_prompts_by_language 方法
        为保持向后兼容性而保留，实际调用新方法
        """
        logger.warning("使用了已废弃的_load_prompts方法，建议改用_load_prompts_by_language")
        return self._load_prompts_by_language(prompt_key, style, None)

    def _load_base_prompts(self) -> Dict[str, str]:
        """
        加载基础提示词模板
        
        :return: 包含评分规则、输出格式、风格模板的字典
        """
        base_prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "conf", "base_prompt.yml")
        try:
            with open(base_prompt_path, "r", encoding="utf-8") as file:
                base_config = yaml.safe_load(file).get("code_review_prompt", {})
                return {
                    "scoring_rules": base_config.get("scoring_rules", ""),
                    "output_format": base_config.get("output_format", ""),
                    "style_template": base_config.get("style_template", ""),
                    "user_prompt_template": base_config.get("user_prompt_template", ""),
                }
        except (FileNotFoundError, yaml.YAMLError) as e:
            logger.error(f"加载基础提示词模板失败: {e}")
            # 返回空字典，后续会回退到默认提示词
            return {}

    def _load_prompts_by_language(self, prompt_key: str, style="professional", language_file: Optional[str] = None) -> Dict[str, Any]:
        """
        根据编程语言加载对应的提示词配置，合并基础模板和语言特定内容
        
        :param prompt_key: 提示词键名
        :param style: 审查风格
        :param language_file: 语言特定的提示词文件名（如 'python_prompt'）
        :return: 提示词配置字典
        """
        # 首先加载基础模板
        base_prompts = self._load_base_prompts()
        if not base_prompts:
            logger.warning("基础提示词模板加载失败，将使用默认提示词")
            return self._load_prompts(prompt_key, style)
        
        # 如果指定了语言文件且文件存在，则合并语言特定的提示词
        language_specific_checks = ""
        user_prompt = base_prompts.get("user_prompt_template", "")
        
        if language_file:
            language_prompt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "conf", f"{language_file}.yml")
            if os.path.exists(language_prompt_path):
                try:
                    with open(language_prompt_path, "r", encoding="utf-8") as file:
                        prompts = yaml.safe_load(file).get(prompt_key, {})
                        
                        # 获取语言特定的审查要点
                        language_specific_checks = prompts.get("language_specific_checks", "")
                        
                        # 如果语言特定文件定义了 user_prompt，则使用它覆盖基础模板
                        if "user_prompt" in prompts:
                            user_prompt = prompts["user_prompt"]
                        
                        logger.info(f"使用 {language_file}.yml 中的语言特定提示词进行审查")
                except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
                    logger.warning(f"加载语言特定提示词失败: {e}，将使用基础模板")
            else:
                logger.warning(f"语言特定提示词文件不存在: {language_prompt_path}，将使用基础模板")
        
        # 使用Jinja2渲染模板
        def render_template(template_str: str) -> str:
            return Template(template_str).render(style=style)
        
        try:
            # 合并 system_prompt：语言特定检查要点 + 基础模板（评分规则、输出格式、风格）
            scoring_rules = render_template(base_prompts["scoring_rules"])
            output_format = render_template(base_prompts["output_format"])
            style_template = render_template(base_prompts["style_template"])
            
            # 组合最终的 system_prompt
            system_prompt_parts = []
            if language_specific_checks:
                # 渲染语言特定检查要点中的 Jinja2 模板变量
                rendered_language_checks = render_template(language_specific_checks)
                system_prompt_parts.append(rendered_language_checks)
            
            system_prompt_parts.extend([
                scoring_rules,
                output_format,
                style_template
            ])
            
            system_prompt = "\n\n".join(system_prompt_parts)
            
            # 渲染 user_prompt
            user_prompt_rendered = render_template(user_prompt)
            
            return {
                "system_message": {"role": "system", "content": system_prompt},
                "user_message": {"role": "user", "content": user_prompt_rendered},
            }
            
        except Exception as e:
            logger.error(f"渲染提示词模板失败: {e}")
            # 回退到默认提示词
            return self._load_prompts(prompt_key, style)

    def call_llm(self, messages: List[Dict[str, Any]]) -> str:
        """调用 LLM 进行代码审核"""
        logger.info(f"向 AI 发送代码 Review 请求, messages: {messages}")
        review_result = self.client.completions(messages=messages)
        
        # 检查返回结果是否为空或无效
        if not review_result or not review_result.strip():
            logger.error("❌ AI 返回结果为空！")
            return "AI 审查失败：返回结果为空，请检查 API 配置和服务状态"
        
        # 检查是否返回了错误消息
        if review_result.startswith("AI 服务暂时不可用"):
            logger.error(f"❌ AI 服务调用失败: {review_result}")
            return review_result
        
        logger.info(f"✅ 收到 AI 返回结果: {review_result[:200]}...")  # 只记录前200字符避免日志过长
        return review_result

    @abc.abstractmethod
    def review_code(self, *args, **kwargs) -> str:
        """抽象方法，子类必须实现"""
        pass


class CodeReviewer(BaseReviewer):
    """代码 Diff 级别的审查"""

    def __init__(self, changes: Optional[List[Dict[str, Any]]] = None):
        """
        初始化 CodeReviewer
        
        :param changes: 代码变更列表，每个元素包含 new_path 等信息
                         如果提供，将根据文件扩展名选择对应的语言特定提示词
        """
        self.client = Factory().getClient()
        self.language_file = self._detect_language_from_changes(changes)
        
        # 统一使用新的提示词加载机制
        self.prompts = self._load_prompts_by_language("code_review_prompt", 
                                                      os.getenv("REVIEW_STYLE", "professional"),
                                                      self.language_file)

    @staticmethod
    def _detect_language_from_changes(changes: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        """
        从代码变更列表中检测主要编程语言
        
        :param changes: 代码变更列表
        :return: 对应的提示词文件名，如果无法检测则返回 None
        """
        if not changes:
            return None
        
        # 统计各语言文件数量
        language_counts = {}
        for change in changes:
            new_path = change.get('new_path', '')
            if not new_path:
                continue
            
            # 获取文件扩展名
            _, ext = os.path.splitext(new_path.lower())
            
            # 查找对应的提示词文件
            if ext in EXTENSION_TO_PROMPT:
                language_file = EXTENSION_TO_PROMPT[ext]
                language_counts[language_file] = language_counts.get(language_file, 0) + 1
        
        if not language_counts:
            logger.info("未识别到支持的编程语言文件，将使用默认提示词")
            return None
        
        # 找出数量最多的语言
        primary_language = max(language_counts.items(), key=lambda x: x[1])[0]
        total_files = sum(language_counts.values())
        primary_count = language_counts[primary_language]
        
        # 如果主要语言占比超过 50%，则使用该语言的提示词
        if primary_count / len(changes) >= 0.5:
            logger.info(f"检测到主要编程语言: {primary_language} ({primary_count}/{len(changes)} 文件)")
            return primary_language
        else:
            # 混合语言，使用默认提示词
            logger.info(f"检测到混合编程语言，主要语言 {primary_language} 占比 {(primary_count/len(changes)*100):.1f}%，将使用默认提示词")
            return None

    def review_and_strip_code(self, changes_text: str, commits_text: str = "", changes: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Review判断changes_text超出取前REVIEW_MAX_TOKENS个token，超出则截断changes_text，
        调用review_code方法，返回review_result，如果review_result是markdown格式，则去掉头尾的```
        
        :param changes_text: 代码变更文本（diff 格式）
        :param commits_text: 提交信息文本
        :param changes: 代码变更列表（用于语言检测，可选）
        :return: 审查结果
        """
        # 如果提供了 changes 且与初始化时的语言不同，则重新加载提示词
        if changes:
            current_language = self._detect_language_from_changes(changes)
            if current_language != self.language_file:
                self.language_file = current_language
                self.prompts = self._load_prompts_by_language("code_review_prompt",
                                                              os.getenv("REVIEW_STYLE", "professional"),
                                                              self.language_file)
        
        # 如果超长，取前REVIEW_MAX_TOKENS个token
        review_max_tokens = int(os.getenv("REVIEW_MAX_TOKENS", 10000))
        # 如果changes为空,打印日志
        if not changes_text:
            logger.info("代码为空, diffs_text = %s", str(changes_text))
            return "代码为空"

        # 计算tokens数量，如果超过REVIEW_MAX_TOKENS，截断changes_text
        tokens_count = count_tokens(changes_text)
        if tokens_count > review_max_tokens:
            changes_text = truncate_text_by_tokens(changes_text, review_max_tokens)

        review_result = self.review_code(changes_text, commits_text).strip()
        
        # 移除markdown代码块包装
        if review_result.startswith("```markdown") and review_result.endswith("```"):
            review_result = review_result[11:-3].strip()
        elif review_result.startswith("```") and review_result.endswith("```"):
            review_result = review_result[3:-3].strip()
        
        # 标准化输出格式，确保符合base_prompt.yml的格式要求
        review_result = self._standardize_output_format(review_result)
        
        return review_result

    def review_code(self, diffs_text: str, commits_text: str = "") -> str:
        """Review 代码并返回结果"""
        messages = [
            self.prompts["system_message"],
            {
                "role": "user",
                "content": self.prompts["user_message"]["content"].format(
                    diffs_text=diffs_text, commits_text=commits_text
                ),
            },
        ]
        return self.call_llm(messages)

    def _standardize_output_format(self, review_text: str) -> str:
        """
        标准化输出格式，确保符合base_prompt.yml的格式要求
        """
        if not review_text:
            return review_text
            
        # 标准化总分格式
        import re
        # 匹配各种可能的总分格式
        score_patterns = [
            r'总分[:：]\s*(\d+)分?',  # 标准格式
            r'总分\s*[:：]?\s*(\d+)',  # 可能的变体
            r'评分[:：]\s*(\d+)分?',   # 错误的"评分"开头
        ]
        
        for pattern in score_patterns:
            match = re.search(pattern, review_text)
            if match:
                score = match.group(1)
                # 替换为标准格式
                review_text = re.sub(pattern, f'【总分】总分:{score}分', review_text)
                break
        
        # 确保有【评分详情】部分
        if '【评分详情】' not in review_text and ('功能实现' in review_text or '/40 分' in review_text):
            # 如果有评分内容但没有标准标题，添加标准标题
            if '功能实现' in review_text:
                review_text = re.sub(r'功能实现[：:]?\s*(\d+)/40\s*分?', 
                                   r'【评分详情】\n- 功能实现：\1/40 分', review_text)
        
        # 标准化问题汇总格式
        if '问题汇总' in review_text and '【问题汇总】' not in review_text:
            review_text = review_text.replace('问题汇总', '【问题汇总】')
        
        # 标准化结论格式
        conclusion_patterns = [
            r'建议[:：]\s*(合并|需要修改|拒绝合并)',
            r'结论[:：]?\s*建议[:：]?\s*(合并|需要修改|拒绝合并)',
        ]
        
        for pattern in conclusion_patterns:
            match = re.search(pattern, review_text)
            if match:
                suggestion = match.group(1)
                # 替换为标准格式
                review_text = re.sub(pattern, f'【结论】\n建议:{suggestion}', review_text)
                break
        
        return review_text

    @staticmethod
    def parse_review_score(review_text: str) -> int:
        """解析 AI 返回的 Review 结果，返回评分"""
        if not review_text:
            return 0
        match = re.search(r"总分[:：]\s*(\d+)分?", review_text)
        return int(match.group(1)) if match else 0

