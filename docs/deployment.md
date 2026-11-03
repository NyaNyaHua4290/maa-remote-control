# 部署说明

## 1. 前置条件

- 一台能跑 Docker 的服务器（1 核 1G 足够，截图多的话建议 2G 内存）
- 一个域名（HTTPS 是硬性要求，原因见下）
- 服务器能访问外网（拉取镜像 / 依赖）

## 2. 用 Docker Compose 启动

```bash
git clone https://github.com/NyaNyaHua4290/maa-remote-control.git
cd maa-remote-control
cp .env.example .env
```

编辑 `.env`，**至少改这两项**：

```dotenv
MAA_REMOTE_SECRET_KEY=<用下面命令生成的随机串>
MAA_REMOTE_PUBLIC_BASE_URL=https://maa.example.com
```

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

> `MAA_REMOTE_SECRET_KEY` 不填也能跑：程序会在数据目录里自动生成 `secret.key` 并复用。
> 但显式指定更稳妥，也方便换卷、重建容器时不丢登录态。

然后：

```bash
docker compose up -d --build
docker compose logs -f        # 看到「已启动」即可 Ctrl+C 退出
```

容器默认只监听 `127.0.0.1:8000`，不直接对外，公网访问交给反向代理。

## 3. 反向代理

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name maa.example.com;

    ssl_certificate     /etc/letsencrypt/live/maa.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/maa.example.com/privkey.pem;

    # 截图任务会把整张图以 Base64 回传，必须放开体积上限
    client_max_body_size 64m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}

server {
    listen 80;
    server_name maa.example.com;
    return 301 https://$host$request_uri;
}
```

### Caddy（自动签发证书，更省事）

```caddyfile
maa.example.com {
    encode gzip
    request_body {
        max_size 64MB
    }
    reverse_proxy 127.0.0.1:8000
}
```

## 4. 数据与备份

所有状态都在 `./data` 目录里：

```
data/
├── maa-remote.db          # SQLite 数据库
├── maa-remote.db-wal      # WAL 日志
└── screenshots/           # 截图
```

热备份 SQLite 用官方推荐方式，避免拷到写了一半的文件：

```bash
docker compose exec maa-remote \
  python -c "import sqlite3; sqlite3.connect('/app/data/maa-remote.db').backup(sqlite3.connect('/app/data/backup.db'))"
```

截图目录直接 `tar` 即可。整个 `data/` 一起打包也行（先停容器最保险）。

## 5. 升级

```bash
git pull
docker compose up -d --build
```

数据库表用 `create_all` 建立，只增不删，正常升级不会丢数据。如果未来表结构有不兼容变更，
升级前先备份 `data/`。

## 6. 换成 PostgreSQL（可选）

多人使用或截图很多时，SQLite 的单写限制会明显起来。改 `.env`：

```dotenv
MAA_REMOTE_DATABASE_URL=postgresql+psycopg://maa:maa@db:5432/maa
```

并在 `docker-compose.yml` 里加一个 `db` 服务，同时把 `psycopg[binary]` 加进 `requirements.txt`。
默认镜像没有装 PostgreSQL 驱动，需要自己构建。

## 7. 关闭注册

部署在公网、只想给固定几个人用时：

```dotenv
MAA_REMOTE_ALLOW_REGISTRATION=false
```

之后新账号由**管理员在网页上创建**：登录管理员账号 → 导航栏「用户管理」→ 新建用户。

如果连管理员都还没创建（`ALLOW_REGISTRATION=false` 时首次部署），也可以在容器里直接写库：

```bash
docker compose exec maa-remote python - <<'PY'
from maa_remote.db import SessionLocal
from maa_remote.models import User
from maa_remote.security import hash_password
from maa_remote.config import generate_user_key

db = SessionLocal()
db.add(User(
    username="admin",
    password_hash=hash_password("换成强密码"),
    user_key=generate_user_key(),
    is_admin=True,
))
db.commit()
print("done")
PY
```

> 注：只要库里一个管理员都没有，服务启动时会自动把最早注册的账号提升为管理员。

## 8. 故障排查

| 现象 | 排查方向 |
| --- | --- |
| 容器起不来 | `docker compose logs` 看是否 `MAA_REMOTE_SECRET_KEY` 缺失或数据库路径不可写 |
| 页面 502 | 反向代理指向的端口不对，或容器没起来 |
| MAA 测试连接失败 | 端点是否 HTTPS、路径是否 `/maa/getTask`、反代是否拦 POST |
| 截图 413 | 反代 `client_max_body_size` 和 `MAA_REMOTE_MAX_PAYLOAD_MB` 都要调大 |
| 登录后立刻退出 | 检查 `MAA_REMOTE_PUBLIC_BASE_URL` 是否是 https，否则 cookie 的 `Secure` 标记与实际协议不匹配 |
