"""数据库迁移脚本 - 清理 review_job 表中的 token 数据

安全说明：
- 此脚本会将所有 token 字段设置为 NULL
- 建议在执行前备份数据库
- 执行后系统将从环境变量获取 token

使用方法：
    python3 scripts/migrate_remove_tokens.py
"""
import sqlite3
import sys
from pathlib import Path


def migrate_remove_tokens(db_path: str = "data/data.db") -> None:
    """清理 review_job 表中的 token 数据"""

    if not Path(db_path).exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        sys.exit(1)

    print(f"📂 数据库路径: {db_path}")

    # 备份提示
    print("\n⚠️  警告：此操作将清除所有存储的 token 数据")
    print("   建议先备份数据库：cp data/data.db data/data.db.backup")
    response = input("\n是否继续？(yes/no): ")

    if response.lower() not in {"yes", "y"}:
        print("❌ 操作已取消")
        sys.exit(0)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 统计当前 token 数据
        cursor.execute("SELECT COUNT(*) FROM review_job WHERE token IS NOT NULL AND token != ''")
        token_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM review_job")
        total_count = cursor.fetchone()[0]

        print(f"\n📊 统计信息:")
        print(f"   总记录数: {total_count}")
        print(f"   包含 token 的记录: {token_count}")

        if token_count == 0:
            print("\n✅ 没有需要清理的 token 数据")
            return

        # 清理 token 数据
        print(f"\n🔄 正在清理 {token_count} 条记录的 token 数据...")
        cursor.execute("UPDATE review_job SET token = NULL WHERE token IS NOT NULL")
        conn.commit()

        # 验证清理结果
        cursor.execute("SELECT COUNT(*) FROM review_job WHERE token IS NOT NULL AND token != ''")
        remaining = cursor.fetchone()[0]

        if remaining == 0:
            print(f"✅ 成功清理 {token_count} 条记录的 token 数据")
            print("\n📝 后续步骤:")
            print("   1. 确保环境变量中配置了以下 token:")
            print("      - GITLAB_ACCESS_TOKEN")
            print("      - GITHUB_ACCESS_TOKEN (如使用 GitHub)")
            print("      - GITEA_ACCESS_TOKEN (如使用 Gitea)")
            print("   2. 重启服务: docker-compose restart 或 systemctl restart ai-codereview")
        else:
            print(f"⚠️  警告：仍有 {remaining} 条记录包含 token")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 迁移失败: {e}")
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    migrate_remove_tokens()
