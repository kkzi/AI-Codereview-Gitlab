# AI Code Review

一个基于大模型的自动化代码审查服务，通过 Git 平台 Webhook 触发审查，结果回写到 MR/PR 或提交记录，并提供 Dashboard 查看记录。

## 功能

- 支持 GitLab / GitHub / Gitea 的 Push 与 MR/PR 事件
- 支持 OpenAI / Anthropic / DeepSeek / 通义千问 / 智谱AI / Ollama
- 异步队列处理 + 失败重试
- Dashboard 查看审查记录与手动重试

## 快速开始

### Docker 部署

1. 准备配置文件

```bash
cp conf/.env.dist conf/.env
```

2. 配置关键参数（示例在 `conf/.env`）

- `SERVER_PORT`：服务端口
- `LLM_CONFIG_PATH`：LLM 配置文件路径（默认 `conf/llm.yml`）
- `DASHBOARD_USER` / `DASHBOARD_PASSWORD`：Dashboard 账号密码
- `PUSH_REVIEW_ENABLED`：是否开启 Push Review
- `GITLAB_ACCESS_TOKEN` / `GITHUB_ACCESS_TOKEN` / `GITEA_ACCESS_TOKEN`（按需）

3. 配置 LLM（示例在 `conf/llm.yml`）

至少设置以下字段之一：

- `LLM_PROVIDER`
- 对应 Provider 的 `*_API_KEY` / `*_API_BASE_URL` / `*_API_MODEL`

4. 启动

```bash
docker-compose up -d
```

5. 验证

- `http://<host>:<port>/health`
- `http://<host>:<port>/dashboard`

### 本地运行（Python 3.10+）

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

配置 `conf/.env` 与 `conf/llm.yml` 后启动：

```bash
python api.py
python worker.py
```

或使用一键启动脚本：

```bash
./start.sh
```

如需单进程运行（API + Worker 同进程）：

```bash
QUEUE_RUN_IN_APP=1 python api.py
```

## Webhook

统一地址：`http://<host>:<port>/review/webhook`

在 GitLab / GitHub / Gitea 中启用 Push 与 MR/PR（Pull Request）事件即可。

## Dashboard

访问：`http://<host>:<port>/dashboard`

账号密码来自 `conf/.env` 的 `DASHBOARD_USER` / `DASHBOARD_PASSWORD`。
生产环境请设置 `DASHBOARD_SECRET_KEY`。
