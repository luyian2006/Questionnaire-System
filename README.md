# Survey System

一个使用 **FastAPI + MongoDB** 实现的在线问卷系统课程项目，面向《大作业一》第一阶段。项目覆盖从账号注册、问卷编辑与发布，到填写者登录答题、服务端校验答题路径、保存答卷和查看统计的核心闭环，并提供可直接在浏览器使用的轻量演示前端。

## 项目功能

- **账号与权限**：用户名唯一；密码使用 PBKDF2 哈希保存；通过 Bearer Token 访问受保护接口；问卷所有者只能管理自己的问卷。
- **问卷管理**：创建、查询、编辑、发布和关闭问卷；支持截止时间、唯一分享标识、匿名展示配置和重复提交配置。
- **版本管理**：发布版本不直接覆盖；修改已发布问卷会基于原定义创建新草稿版本，历史版本保留。
- **题目类型**：单选、多选、文本和数值题；选项题、文本长度和数值范围等约束在服务端校验。
- **条件跳转**：按题目顺序和规则优先级计算下一题；发布前校验问卷定义，最终提交时由服务端重新计算实际作答路径。
- **答卷与统计**：答卷保存至 MongoDB；支持单选/多选选项计数、文本答案查看、数值平均值，以及整体或单题统计。
- **浏览器演示页**：提供注册登录、问卷管理、分享答题和统计查看，不需要单独安装前端构建工具。

### 匿名填写与访问边界

本项目中的“匿名填写”指填写者仍需登录，但问卷所有者不能通过统计接口查看填写者身份。系统内部保留填写者标识，用于身份认证和重复提交控制。已发布且开放的分享问卷定义可公开读取；答题导航与提交需要登录。

默认禁止同一账号对同一问卷重复提交。问卷设置 `allow_multiple_submissions=true` 后允许重复提交。关闭或超过截止时间的问卷不能继续读取分享内容、导航或提交。

## 项目结构

```text
app/
  algorithms/       答案校验、问卷定义校验、跳转与提交路径算法
  core/             配置与认证安全工具
  db/               MongoDB 客户端、集合访问和索引
  api.py            FastAPI 路由
  services.py       用户、问卷、答卷和统计业务逻辑
  main.py           应用入口、生命周期、静态前端和健康检查
frontend/           轻量演示前端（HTML、CSS、JavaScript）
tests/              算法、API 业务和健康检查测试
docs/               系统、数据库、API、算法、测试报告
requirements.txt    Python 运行和测试依赖
.env.example        本地环境变量示例
```

主要接口及请求示例见 [API 文档](docs/api.md)；MongoDB 集合与索引说明见 [数据库设计](docs/database-design.md)；核心跳转规则见 [跳转算法说明](docs/jump-algorithm.md)。

## 环境要求

- Windows 开发环境
- Python 3.10.7
- MongoDB 已安装并运行
- Git

## 安装依赖

建议在项目根目录使用虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果需要重新创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 本地配置

复制 `.env.example` 为 `.env`，按需修改 MongoDB 连接信息：

```powershell
Copy-Item .env.example .env
```

默认配置：

```text
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=survey_system
AUTH_SECRET=development-only-change-me
```

## 启动服务

```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

服务默认地址：

```text
http://127.0.0.1:8000
```

## 接口访问

启动后可访问 Swagger API 文档：

```text
http://127.0.0.1:8000/docs
```

主要接口见 [docs/api.md](docs/api.md)。基本流程是：注册并登录，携带 `Authorization: Bearer <token>` 创建问卷，编辑题目，发布后使用 `share_slug` 查询和答题，最后由所有者查看统计。

接口按业务流程分为四组：

| 分组 | 接口 |
| --- | --- |
| 认证 | `POST /auth/register`、`POST /auth/login` |
| 问卷管理 | `POST /surveys`、`GET /surveys`、`GET/PATCH /surveys/{survey_id}`、`POST /surveys/{survey_id}/publish`、`POST /surveys/{survey_id}/close` |
| 分享答题 | `GET /surveys/share/{share_slug}`、`POST /surveys/share/{share_slug}/next`、`POST /surveys/share/{share_slug}/submit` |
| 统计与健康 | `GET /surveys/{survey_id}/statistics`、`GET /health`、`GET /health/db` |

问卷创建、编辑、发布、关闭和统计接口需要所有者身份；分享定义的 GET 接口不要求登录，但导航和提交接口需要填写者登录。错误答案、路径外答案和非法配置会返回结构化错误信息，具体请求与响应见 [API 文档](docs/api.md)。

## 简单前端

启动 FastAPI 后访问 `http://127.0.0.1:8000/`，可以使用内置的轻量演示页面完成注册/登录、创建和编辑问卷、设置截止时间、发布/关闭、发布新版本、复制分享标识、答题提交，以及全部版本或指定版本的统计查看。问卷发布后才会显示可复制的填写链接。页面直接调用同源 API，不需要额外的 Node.js 构建步骤；完整接口仍可通过 `/docs` 查看。

服务健康检查：

```text
GET http://127.0.0.1:8000/health
```

MongoDB 连接检查：

```text
GET http://127.0.0.1:8000/health/db
```

`/health/db` 会执行 MongoDB `ping` 命令。连接失败时返回 `503` 和简洁错误信息。

## MongoDB

Windows 示例：

```powershell
New-Item -ItemType Directory -Force D:\MongoDB\data\survey-system | Out-Null
D:\MongoDB\Server\8.3\bin\mongod.exe --dbpath D:\MongoDB\data\survey-system --port 27017
```

应用启动时会创建 users、surveys、responses 所需索引。MongoDB 不可用时 `/health` 仍可运行，`/health/db` 会返回 503。

## 运行测试

```powershell
.\.venv\Scripts\pytest.exe
```

也可以直接使用当前 Python 环境运行：

```powershell
python -m pytest -q
```

### 测试内容

| 测试文件 | 覆盖内容 |
| --- | --- |
| `tests/test_answer_validator.py` | 四种题型、必答/缺失、选项、重复选择、文本长度、数值边界和有限性 |
| `tests/test_survey_validator.py` | 题目与选项定义、顺序、规则优先级、条件兼容性、目标和循环配置 |
| `tests/test_jump.py` | 默认导航、条件跳转、`end`、非法答案、乱序题目和规则优先级 |
| `tests/test_submission_validation.py` | 服务端实际路径、必答跳过、路径外答案、未知题目、非法目标、循环和最大步数 |
| `tests/test_api_business.py` | 注册登录、权限隔离、问卷版本、发布/关闭、答题提交、截止时间、重复提交和四类统计 |
| `tests/test_health.py` | 健康检查、前端入口和 MongoDB 健康检查响应 |

自动化测试默认使用内存数据库替身，MongoDB 健康检查使用 mock，因此不要求本地启动真实 MongoDB。最近一次完整回归的实际结果为：

```text
129 passed, 3 warnings
```

警告来自当前 FastAPI/Starlette 与 httpx 的兼容性提示，以及旧版 422 状态常量弃用提示，未阻断测试。若要单独运行某一层测试，可使用：

```powershell
python -m pytest tests/test_jump.py -q
python -m pytest tests/test_submission_validation.py -q
python -m pytest tests/test_api_business.py -q
```

真实 HTTP 和 MongoDB 验收使用隔离数据库 `survey_system_browser_test`，通过 Swagger UI 发起请求并用 `mongosh` 只读核对，记录见 [真实业务测试报告](docs/business-test-report.md)。该验收没有删除或覆盖默认数据库数据。

## 第一阶段范围

- 支持单选、多选、文本和数字题。
- 发布前校验题目、选项、跳转规则和循环。
- 已发布版本不可直接覆盖，编辑会创建新的草稿版本。
- 填写者需要登录；`allow_anonymous` 表示对问卷所有者隐藏填写者身份，不是系统级匿名。
- 默认禁止同一账号重复提交；`allow_multiple_submissions=true` 时允许重复提交。

## 已知限制

- `start_question_id` 尚未实现，提交路径默认从按 `order` 排序后的第一题开始。
- 当前没有进行中的答卷会话、答卷明细导出或所有者查看原始答卷身份的接口。
- 统计支持按版本筛选，但默认跨版本合并统计策略尚未定义为独立业务契约。
- 自动化 API 测试使用内存数据库替身；真实 MongoDB 已完成一轮隔离验收，但未覆盖并发压力、故障恢复和生产部署。

## 课程文档

- [第一阶段最终实验报告](docs/phase1-final-report.md)
- [第一阶段差距检查](docs/phase1-gap-check.md)
- [真实业务测试报告](docs/business-test-report.md)
- [系统设计](docs/system-design.md)
- [数据库设计](docs/database-design.md)
- [API 文档](docs/api.md)
- [跳转算法说明](docs/jump-algorithm.md)
- [AI 使用日志](docs/ai-usage-log.md)
