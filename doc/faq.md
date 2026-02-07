## 常见问题

### Docker 容器部署时，更新 .env 文件后不生效

**可能原因**

容器环境变量只在启动时读取，修改 `conf/.env` 后需要重启容器生效。

**解决方案**

- 删除现有容器：

```
docker rm -f <container_name>
```

重新创建并启动容器：

```
docker-compose up -d
```

或参考说明文档启动容器。  
说明：`conf/llm.yml` 使用 mtime 缓存机制，通常修改后可自动生效；如未生效再重启容器。

### GitLab 配置 Webhooks 时提示 "Invalid url given"

**可能原因**

GitLab 默认禁止 Webhooks 访问本地网络地址。

**解决方案**

- 进入 GitLab 管理区域：Admin Area → Settings → Network。
- 在 Outbound requests 部分，勾选 Allow requests to the local network from webhooks and integrations。
- 保存。

### 如何让不同项目的消息发送到不同的群？

**解决方案**

在项目的 .env 文件中，配置不同项目或不同平台实例的 Webhook 地址。
以 DingTalk 为例，配置如下：

```
DINGTALK_ENABLED=1
#项目A的群机器人的Webhook地址（项目名会被转为大写）
DINGTALK_WEBHOOK_URL_PROJECT_A=https://oapi.dingtalk.com/robot/send?access_token={access_token_of_project_a}
#项目B的群机器人的Webhook地址
DINGTALK_WEBHOOK_URL_PROJECT_B=https://oapi.dingtalk.com/robot/send?access_token={access_token_of_project_b}
#保留默认WEBHOOK_URL，未匹配的项目将使用此URL
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token={access_token}
```

飞书和企业微信的配置方式类似。

### 如何让不同的Gitlab服务器的消息发送到不同的群？

在项目的 .env 文件中，配置不同实例的 Webhook 地址。当前使用 `url_slug` 作为匹配键：
`url_slug` 为实例基址去掉协议后，将非字母数字替换为下划线，例如：
`https://gitlab.example.com` → `gitlab_example_com`

以 DingTalk 为例，配置如下：

```
DINGTALK_ENABLED=1
# Gitlab服务器A(http://192.168.30.164)的群机器人的Webhook地址
DINGTALK_WEBHOOK_URL_192_168_30_164=https://oapi.dingtalk.com/robot/send?access_token={access_token_of_gitlab_server_a}
# Gitlab服务器B(http://example.gitlab.com)的群机器人的Webhook地址
DINGTALK_WEBHOOK_URL_example_gitlab_com=https://oapi.dingtalk.com/robot/send?access_token={access_token_of_gitlab_server_b}
```

飞书和企业微信的配置方式类似。  
**优先级：** 先按项目名匹配，再按实例 `url_slug` 匹配，最后使用默认地址。

### docker 容器部署时，连接Ollama失败

**可能原因**

配置127.0.0.1:11434连接Ollama。由于docker容器的网络模式为bridge，容器内的127.0.0.1并不是宿主机的127.0.0.1，所以连接失败。

**解决方案**

在 `conf/llm.yml` 中修改 `OLLAMA_API_BASE_URL` 为宿主机的 IP 地址或外网 IP 地址。同时要配置 Ollama 服务绑定到宿主机 IP（或 0.0.0.0）。

```
OLLAMA_API_BASE_URL=http://127.0.0.1:11434  # 错误
OLLAMA_API_BASE_URL=http://{宿主机/外网IP地址}:11434  # 正确
```

### 如何配置企业微信和飞书消息推送？

**1.配置企业微信推送**

- 在企业微信群中添加一个自定义机器人，获取 Webhook URL。

- 更新 .env 中的配置：
  ```
  #企业微信配置
  WECOM_ENABLED=1  #0不发送企业微信消息，1发送企业微信消息
  WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx  #替换为你的Webhook URL
  ```

**2.配置飞书推送**

- 在飞书群中添加一个自定义机器人，获取 Webhook URL。
- 更新 .env 中的配置：
  ```
  #飞书配置
  FEISHU_ENABLED=1
  FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx #替换为你的Webhook URL
  ```

### 是否支持对 GitHub 代码库的 Review？

是的，支持。 需完成以下配置：

**1.配置Github Webhook**

- 进入你的 GitHub 仓库 → Settings → Webhooks → Add webhook。
    - Payload URL: http://your-server-ip:5001/review/webhook（替换为你的服务器地址）
    - Content type选择application/json
    - 在 Which events would you like to trigger this webhook? 中勾选 Push 和 Pull request
    - 点击 Add webhook 完成配置。

**2.生成 GitHub Personal Access Token**

- 进入 GitHub 个人设置 → Developer settings → Personal access tokens → Generate new token。
- 选择 Fine-grained tokens 或 tokens (classic) 都可以
- 点击 Create new token
- Repository access根据需要选择
- Permissions需要选择Commit statuses、Contents、Discussions、Issues、Metadata和Pull requests
- 点击 Generate token 完成配置。

**3.配置.env文件**

- 在.env文件中，配置GITHUB_ACCESS_TOKEN：
  ```
  GITHUB_ACCESS_TOKEN=your-access-token  #替换为你的Access Token
  ```

### 是否支持对 Gitea 代码库的 Review？

是的，支持。配置方式与 GitHub 类似：

- 进入 Gitea 仓库 → Settings → Webhooks → Add webhook
  - URL: http://your-server-ip:5001/review/webhook
  - Events：勾选 Push 和 Pull Request
- 在 `.env` 中配置 `GITEA_ACCESS_TOKEN`
