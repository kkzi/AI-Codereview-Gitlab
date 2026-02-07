"""Webhook 签名验证工具"""
import hmac
import hashlib
from typing import Optional


def verify_gitlab_signature(payload: bytes, token: str, secret: Optional[str] = None) -> bool:
    """
    验证 GitLab webhook 签名

    GitLab 使用 X-Gitlab-Token header 传递 token

    Args:
        payload: 请求体（bytes）
        token: X-Gitlab-Token header 的值
        secret: 配置的 webhook secret（从环境变量获取）

    Returns:
        bool: 签名是否有效
    """
    if not secret:
        # 如果没有配置 secret，则不验证（向后兼容）
        return True

    # GitLab 使用简单的 token 比较
    return hmac.compare_digest(token or "", secret)


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    验证 GitHub webhook 签名

    GitHub 使用 HMAC-SHA256 签名
    Header: X-Hub-Signature-256: sha256=<signature>

    Args:
        payload: 请求体（bytes）
        signature: X-Hub-Signature-256 header 的值
        secret: 配置的 webhook secret

    Returns:
        bool: 签名是否有效
    """
    if not secret or not signature:
        return False

    # 计算期望的签名
    expected_signature = "sha256=" + hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    # 使用时间安全的比较
    return hmac.compare_digest(signature, expected_signature)


def verify_gitea_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    验证 Gitea webhook 签名

    Gitea 使用 HMAC-SHA256 签名
    Header: X-Gitea-Signature: <signature>

    Args:
        payload: 请求体（bytes）
        signature: X-Gitea-Signature header 的值
        secret: 配置的 webhook secret

    Returns:
        bool: 签名是否有效
    """
    if not secret or not signature:
        return False

    # 计算期望的签名
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    # 使用时间安全的比较
    return hmac.compare_digest(signature, expected_signature)
