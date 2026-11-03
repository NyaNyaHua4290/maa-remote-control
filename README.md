# MAA 远程控制

> **本项目由 AI 生成。** 代码、文档与测试均由 AI 助手（DeepSeek Harness）依据
> [MAA 官方远程控制协议](https://docs.maa.plus/zh-cn/protocol/remote-control-schema.html)
> 编写，已经过本地测试，但尚未经过大规模生产环境验证。使用前请自行审阅代码，风险自负。

一个可以自托管的网页版 MAA 控制器：把 MAA 挂在任何一台机器上（Windows 桌面、家里的小主机、云服务器），
然后在浏览器里统一查看状态、下发任务、看截图。支持多账号，每个账号可以接不限数量的 MAA 实例。

[![CI](https://github.com/NyaNyaHua4290/maa-remote-control/actions/workflows/ci.yml/badge.svg)](https://github.com/NyaNyaHua4290/maa-remote-control/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)

---

## 它做了什么

MAA 从 v5 开始内置了「远程控制」功能：MAA 以固定间隔（默认 1 秒）向你自己提供的一个 HTTP 服务轮询任务，
执行完再把结果回报过去。本项目就是那个服务：

```
┌──────────┐   1. POST /maa/getTask      ┌─────────────────┐
│          │ ──────────────────────────▶ │                 │
│   MAA    │                             │  MAA 远程控制    │◀── 浏览器（你）
│ (被控端) │ ◀────────────────────────── │  FastAPI + SQLite│
│          │   2. 返回 tasks 列表         │                 │
│          │                             │                 │
│          │   3. POST /maa/reportStatus │                 │
│          │ ──────────────────────────▶ │                 │
└──────────┘   （截图任务会把图片回传）    └─────────────────┘
```

### 功能

- **多账号**：用户名 + 密码注册登录，数据互相隔离。
- **多实例**：同一个账号可以接多台 MAA，MAA 首次轮询时自动登记，可以给它们起名字（官服 / B服 / 小号）。
- **在线状态**：30 秒内有过轮询就算在线，页面每 5 秒自动刷新。
- **任务下发**：一键长草、单独跑某个子功能、抽卡、生息演算、截图、停止当前任务、修改连接地址/关卡。
- **截图查看**：截图任务的结果自动落盘，页面上点开即看。
- **任务历史**：每条任务的类型、参数、状态、完成时间、错误信息都留在库里。
- **开箱即用**：一条 `docker compose up -d` 就能跑，数据落到宿主机目录。

## 快速开始（Docker，推荐）

```bash
git clone https://github.com/NyaNyaHua4290/maa-remote-control.git
cd maa-remote-control

cp .env.example .env
# 生成一个随机密钥并填进 .env 的 MAA_REMOTE_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 改成你真正对外访问的地址，会显示在配置指引页里
# MAA_REMOTE_PUBLIC_BASE_URL=https://maa.example.com

docker compose up -d
```

打开 `http://127.0.0.1:8000` 注册账号，然后照着页面里的「配置指引」把端点填进 MAA：

| MAA 设置项（设置 → 远程控制） | 填什么 |
| --- | --- |
| 用户标识符 | 网页「配置指引」里给你的那串密钥 |
| 获取任务端点 | `https://你的域名/maa/getTask` |
| 汇报任务端点 | `https://你的域名/maa/reportStatus` |
| 轮询间隔 | `1000`（毫秒，默认值即可） |

MAA 保存后几秒内就会出现在首页。

> ⚠️ **务必用 HTTPS。** MAA 检测到 http 端点时每次连接都会弹不安全警告，明文传输也会泄露你的用户标识符。

## 本地开发

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux / macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .

# 起服务（自动创建 data/maa-remote.db）
uvicorn maa_remote.main:app --reload

# 跑测试
pytest
```

前端是服务端渲染的 Jinja2 模板 + 原生 JS，没有 Node 构建步骤，改完模板刷新即可。

## 配置项

所有配置都通过环境变量注入（见 [.env.example](.env.example)）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MAA_REMOTE_SECRET_KEY` | `dev-only-insecure-secret-change-me` | 会话签名密钥，**生产环境必改**，不然后台告警且任何人可伪造登录态 |
| `MAA_REMOTE_DATABASE_URL` | `sqlite:///data/maa-remote.db` | 数据库连接串，也支持 PostgreSQL |
| `MAA_REMOTE_DATA_DIR` | `./data` | 数据目录（数据库 + 截图） |
| `MAA_REMOTE_PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | 对外访问地址，用于在页面上生成端点 |
| `MAA_REMOTE_ALLOW_REGISTRATION` | `true` | 是否开放注册；设为 `false` 后只能由管理员建号 |
| `MAA_REMOTE_SESSION_MAX_AGE` | `1209600`（14 天） | 登录态有效期（秒） |
| `MAA_REMOTE_MAX_PAYLOAD_MB` | `64` | 单次回报的体积上限，截图任务需要足够大 |
| `MAA_REMOTE_LOG_LEVEL` | `INFO` | 日志级别 |

## 项目结构

```
maa-remote-control/
├── Dockerfile                  # 多阶段构建，非 root 运行
├── docker-compose.yml          # 一键部署
├── pyproject.toml              # 包元数据与 pytest 配置
├── requirements.txt            # 运行依赖
├── requirements-dev.txt        # 测试依赖
├── docs/
│   ├── deployment.md           # 反向代理、HTTPS、备份、升级
│   └── protocol.md             # 协议细节与 curl 示例
├── src/maa_remote/
│   ├── main.py                 # FastAPI 应用装配
│   ├── config.py               # 环境变量 → Settings
│   ├── db.py                   # 引擎、会话、建表
│   ├── models.py               # User / Device / Task
│   ├── security.py             # bcrypt、会话、CSRF
│   ├── web.py                  # Jinja2 环境与过滤器
│   ├── api/
│   │   ├── maa.py              # 协议的 getTask / reportStatus
│   │   ├── pages.py            # 页面路由
│   │   └── app_api.py          # 页面轮询用的只读 JSON
│   ├── services/               # 任务队列、设备登记、截图落盘
│   ├── templates/              # 页面模板
│   └── static/                 # CSS 与 JS
└── tests/                      # pytest 单元 / 集成测试
```

## 安全须知

1. **必须 HTTPS**，并在反向代理上限制请求体（Nginx：`client_max_body_size 64m;`）。
2. **用户标识符等于口令**，泄露后别人可以给你的 MAA 下发任务（包括改连接地址）。泄露了就在数据库里换一个。
3. **MAA 端点是匿名接口**，没有 CSRF 保护，这是协议决定的；防护手段只有 HTTPS + 足够长的随机密钥。
4. 默认使用 SQLite，单机够用；多人同时使用建议换 PostgreSQL。
5. 不要把这个服务直接暴露在公网 80 端口，请走反向代理并启用 TLS。

## 常见问题

**Q：MAA 里点「测试连接」提示失败？**
A：先确认 `用户标识符` 是否和网页上完全一致（不要有空格），再看端点地址是不是 `https://域名/maa/getTask`，最后检查反向代理有没有拦住 POST。

**Q：任务一直显示「已下发」然后变「超时」？**
A：说明 MAA 收到了任务但没回报结果，通常是 MAA 弹了窗口、模拟器断了或者任务执行时间超过 15 分钟。MAA 那边的日志（`debug/gui.log`）会有具体原因。

**Q：截图任务失败了，payload 里没有图片？**
A：检查反向代理的请求体上限，以及 `MAA_REMOTE_MAX_PAYLOAD_MB` 是否够大。截图以 Base64 传输，体积约为原图的 1.33 倍。

**Q：能同时接官服和 B 服吗？**
A：可以，同一个账号下接多台 MAA 就行，它们共用一个用户标识符，靠设备标识符区分。

## 致谢

- [MAA - MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights)：明日方舟小助手
- [远程控制协议文档](https://docs.maa.plus/zh-cn/protocol/remote-control-schema.html)：本项目的协议依据

## 许可证

[MIT](LICENSE)

---

**再次声明：本仓库由 AI 生成。** 它不是 MAA 官方项目，与 MaaAssistantArknights 团队没有隶属关系；
使用前请自行审阅代码并承担相应风险。
