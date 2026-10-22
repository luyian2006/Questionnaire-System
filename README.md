# Survey System

基于 MongoDB 的问卷系统课程项目。当前版本实现第一阶段核心业务闭环：注册登录、问卷版本管理、发布与关闭、条件跳转、答案路径验证、答卷持久化和统计。

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

自动化测试默认使用内存数据库替身和 MongoDB 健康检查 mock，不要求启动真实 MongoDB。真实浏览器和 MongoDB 验证记录在 [docs/business-test-report.md](docs/business-test-report.md)。

## 第一阶段范围

- 支持单选、多选、文本和数字题。
- 发布前校验题目、选项、跳转规则和循环。
- 已发布版本不可直接覆盖，编辑会创建新的草稿版本。
- 填写者需要登录；`allow_anonymous` 表示对问卷所有者隐藏填写者身份，不是系统级匿名。
- 默认禁止同一账号重复提交；`allow_multiple_submissions=true` 时允许重复提交。
