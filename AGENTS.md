# Repository Guidelines

## 项目结构与模块组织

本仓库是一个基于 Flask 的 AI 代码审查服务。入口文件包括 `api.py`（HTTP 服务）和 `worker.py`（队列 Worker），`start.sh` 会同时启动两者。核心业务代码位于 `app/`：`app/api/` 负责路由与鉴权，`app/usecases/` 编排审查流程，`app/infra/` 封装队列、数据库、通知、SCM 与 LLM 客户端，`app/domain/` 存放领域模型。测试位于 `app/tests/unit/` 与 `app/tests/integration/`。配置样例和提示词在 `conf/`，页面模板在 `templates/`，前端静态资源在 `static/`，运行数据与日志分别写入 `data/` 和 `log/`。

## 构建、测试与本地开发命令

- `python -m venv .venv && source .venv/bin/activate`：创建并启用本地虚拟环境。
- `pip install -r requirements.txt`：安装 Python 依赖。
- `cp conf/.env.dist conf/.env`：初始化环境变量配置，随后补充 Git 平台、Dashboard 与 LLM 参数。
- `python api.py`：启动 Flask API 服务。
- `python worker.py`：启动后台队列处理进程。
- `./start.sh`：本地同时启动 API 与 Worker。
- `QUEUE_RUN_IN_APP=1 python api.py`：以单进程模式运行 API 与 Worker。
- `docker-compose up -d`：构建并启动容器化服务。
- `python -m unittest discover -s app/tests`：运行全部测试。

## 编码风格与命名约定

代码与注释使用英文，文档使用中文。Python 代码遵循 PEP 8，使用 4 空格缩进；模块、函数、变量使用 `snake_case`，类使用 `PascalCase`，常量和环境变量使用 `UPPER_SNAKE_CASE`。新增配置优先放入 `conf/.env.dist` 或对应的 YAML 文件，并在读取处提供清晰默认值或校验。保持分层边界清晰：路由只处理请求和响应，业务编排放在 `usecases`，外部系统适配放在 `infra`。

## 测试指南

测试基于标准库 `unittest`，文件命名采用 `test_*.py`，测试类使用 `Test*`，测试方法使用 `test_*`。单元测试应优先 mock 外部 API、数据库和网络调用；集成测试可使用临时 SQLite 文件或 Flask 测试客户端。修改 Webhook、安全校验、队列、LLM 工厂或通知逻辑时，应补充对应的单元测试，并运行 `python -m unittest discover -s app/tests`。

## 提交与 Pull Request 规范

近期提交信息以简短英文描述为主，例如 `Add worker stats toast and dashboard entry`，也存在版本号提交如 `v2.1.0`。建议使用祈使句、单行摘要，聚焦行为变化。PR 应说明变更目的、关键实现、测试结果，以及涉及的配置项或迁移步骤；修改 Dashboard 或页面模板时附截图；关联 issue 或需求编号；不要提交真实 token、密钥、运行数据库或日志内容。

## 安全与配置提示

生产环境必须设置强 `DASHBOARD_SECRET_KEY` 和非默认 Dashboard 密码。GitLab、GitHub、Gitea 与 LLM 的访问密钥只放在 `conf/.env` 或部署平台的 secret 管理中，不写入代码、测试夹具或文档示例。Webhook 相关改动需保留签名校验路径，并覆盖成功与失败场景。
