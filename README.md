![Push图片](doc/img/open/ai-codereview-cartoon.png)

## 项目简介

本项目是一个基于大模型的自动化代码审查工具，帮助开发团队在代码合并或提交时，快速进行智能化的审查(Code Review)，提升代码质量和开发效率。

当前版本：2.1.0

## 功能

- 🔗 多平台支持
  - 支持 GitLab / GitHub / Gitea 的 Push 与 MR/PR 事件。
- 🚀 多模型支持
  - 兼容 DeepSeek、ZhipuAI、OpenAI、Anthropic、通义千问 和 Ollama，想用哪个就用哪个。
- 🧵 异步队列 + 失败重试
  - Webhook 入队异步处理，任务失败自动重试。
- 📢 消息即时推送
  - 审查结果一键直达 钉钉、企业微信 或 飞书，代码问题无处可藏！
- 📊 可视化 Dashboard
  - 集中展示所有 Code Review 记录，项目统计、开发者统计，数据说话，甩锅无门！
- 🎭 Review Style 任你选
  - 专业型 🤵：严谨细致，正式专业。 
  - 讽刺型 😈：毒舌吐槽，专治不服（"这代码是用脚写的吗？"） 
  - 绅士型 🌸：温柔建议，如沐春风（"或许这里可以再优化一下呢~"） 
  - 幽默型 🤪：搞笑点评，快乐改码（"这段 if-else 比我的相亲经历还曲折！"）

**效果图:**

![MR图片](doc/img/open/mr.png)

![Note图片](doc/img/open/note.jpg)

![Dashboard图片](doc/img/open/dashboard.jpg)

## 原理

当用户在 GitLab / GitHub / Gitea 上提交代码（如 Merge/Pull Request 或 Push）时，平台将触发
webhook 调用本系统接口。系统随后通过大模型对代码进行审查，并将结果回写到对应的 MR/PR 或 Commit
Note 中，便于团队查看和处理。

![流程图](doc/img/open/process.png)

## 部署

### 方案一：Docker 部署

**1. 准备环境文件**

- 克隆项目仓库：
```aiignore
git clone https://github.com/sunmh207/AI-Codereview-Gitlab.git
cd AI-Codereview-Gitlab
```

- 创建配置文件：
```aiignore
cp conf/.env.dist conf/.env
```

- 编辑 conf/.env 文件，配置以下关键参数：

```bash
#服务端口
SERVER_PORT=5001

#LLM 配置文件路径（默认 conf/llm.yml）
LLM_CONFIG_PATH=conf/llm.yml

#支持review的文件类型（未配置的不会审查）
SUPPORTED_EXTENSIONS=.java,.py,.go,.js,.ts,.vue,.sql,.md

#Review 风格：professional | sarcastic | gentle | humorous
REVIEW_STYLE=professional

#Git 平台 Token（按需填写）
GITLAB_ACCESS_TOKEN={YOUR_GITLAB_ACCESS_TOKEN}
GITHUB_ACCESS_TOKEN={YOUR_GITHUB_ACCESS_TOKEN}
GITEA_ACCESS_TOKEN={YOUR_GITEA_ACCESS_TOKEN}

#Push Review 开关
PUSH_REVIEW_ENABLED=1
#仅评审合并到受保护分支的 MR/PR
MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED=0

#钉钉消息推送: 0不发送钉钉消息，1发送钉钉消息
DINGTALK_ENABLED=0
DINGTALK_WEBHOOK_URL={YOUR_WDINGTALK_WEBHOOK_URL}
```

LLM 配置在 `conf/llm.yml`，示例：

```yaml
LLM_PROVIDER: openai
OPENAI_API_KEY: sk-xxx
OPENAI_API_MODEL: gpt-4o-mini
OPENAI_API_BASE_URL: https://api.openai.com/v1
```

**2. 启动服务**

```bash
docker-compose up -d
```

默认会启动 app + worker 两个服务，确保队列任务被处理。

**3. 验证部署**

- 主服务验证：
  - 访问 http://your-server-ip:5001/health
  - 返回 `{"status":"ok"}` 说明服务启动成功。
- Dashboard 验证：
  - 访问 http://your-server-ip:5001/dashboard
  - 看到一个审查日志页面，说明 Dashboard 启动成功。

### 方案二：本地Python环境部署

**1. 获取源码**

```bash
git clone https://github.com/sunmh207/AI-Codereview-Gitlab.git
cd AI-Codereview-Gitlab
```

**2. 安装依赖**

使用 Python 环境（建议使用 `uv venv` 创建虚拟环境）安装项目依赖(Python 版本：3.10+):

```bash
# 创建虚拟环境（推荐使用 uv）
uv venv

# 激活虚拟环境
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

**3. 配置环境变量**

同 Docker 部署方案中的.env 文件配置。

**4. 启动服务**

```bash
python api.py
python worker.py
```

也可以使用一键启动脚本：

```bash
./start.sh
```

服务启动后，可以访问：
- Webhook API：`http://localhost:5001/review/webhook`
- Dashboard：`http://localhost:5001/dashboard`（默认账号：admin/admin）

如需单进程启动，可使用：`QUEUE_RUN_IN_APP=1 python api.py`。

启动时会自动对账最近 7 天的 webhook 事件，发现“没有评审记录且没有 pending/running 任务”的事件会自动重新入列（可用 `RECONCILE_ON_STARTUP=0` 关闭）。

### 配置 Git 平台 Webhook

统一 Webhook URL：`http://your-server-ip:5001/review/webhook`

#### GitLab

#### 1. 创建Access Token

方法一：在 GitLab 个人设置中，创建一个 Personal Access Token。

方法二：在 GitLab 项目设置中，创建Project Access Token

#### 2. 配置 Webhook

在 GitLab 项目设置中，配置 Webhook：

- URL：http://your-server-ip:5001/review/webhook
- Trigger Events：勾选 Push Events 和 Merge Request Events (不要勾选其它Event)
- Secret Token：上面配置的 Access Token(可选)

**备注**

1. Token使用优先级
  - 系统优先使用 .env 文件中的 GITLAB_ACCESS_TOKEN。
  - 如果 .env 文件中没有配置 GITLAB_ACCESS_TOKEN，则使用 Webhook 传递的Secret Token。
2. 网络访问要求
  - 请确保 GitLab 能够访问本系统。
  - 若内网环境受限，建议将系统部署在外网服务器上。

#### GitHub

- 进入 GitHub 仓库 → Settings → Webhooks → Add webhook
- Payload URL：http://your-server-ip:5001/review/webhook
- Content type：application/json
- Events：勾选 Push 和 Pull request
- Token：在 `conf/.env` 中配置 `GITHUB_ACCESS_TOKEN`（也可通过 `X-GitHub-Token` 传入）

#### Gitea

- 进入 Gitea 仓库 → Settings → Webhooks → Add webhook
- URL：http://your-server-ip:5001/review/webhook
- Events：勾选 Push 和 Pull Request
- Token：在 `conf/.env` 中配置 `GITEA_ACCESS_TOKEN`（也可通过 `X-Gitea-Token` 传入）

### 配置消息推送

#### 1.配置钉钉推送

- 在钉钉群中添加一个自定义机器人，获取 Webhook URL。
- 更新 .env 中的配置：
  ```
  #钉钉配置
  DINGTALK_ENABLED=1  #0不发送钉钉消息，1发送钉钉消息
  DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxx #替换为你的Webhook URL
  ```

企业微信和飞书推送配置类似，具体参见 [常见问题](doc/faq.md)

## 常见问题

**1.如何对整个代码库进行Review?**

2.1.0 版本暂未提供 CLI 全量扫描，建议通过 Git 平台 webhook 触发审查。

**2.其它常见问题**

参见 [常见问题](doc/faq.md)

## 交流

若本项目对您有帮助，欢迎 Star ⭐️ 或 Fork。 有任何问题或建议，欢迎提交 Issue 或 PR。

也欢迎加微信/微信群，一起交流学习。

<p float="left">
  <img src="doc/img/open/wechat.jpg" width="400" />
  <img src="doc/img/open/wechat_group.jpg" width="400" /> 
</p>

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=sunmh207/AI-Codereview-Gitlab&type=Timeline)](https://www.star-history.com/#sunmh207/AI-Codereview-Gitlab&Timeline)
