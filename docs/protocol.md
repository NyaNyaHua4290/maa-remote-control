# 协议实现说明

本项目的接口严格遵循 MAA 官方文档：[远程控制协议](https://docs.maa.plus/zh-cn/protocol/remote-control-schema.html)。
下面记录的是「本项目具体怎么实现」的细节，方便排障和二次开发。

## 端点总览

| 方法 | 路径 | 鉴权 | 用途 |
| --- | --- | --- | --- |
| POST | `/maa/getTask` | 无（靠 `user` 密钥） | MAA 轮询取任务 |
| POST | `/maa/reportStatus` | 无（靠 `user` 密钥） | MAA 回报结果 |
| GET | `/` | 登录 | 实例列表 |
| GET | `/devices/{id}` | 登录 | 实例详情与任务记录 |
| GET | `/devices/{id}/screenshot/{task_id}` | 登录 | 查看截图 |
| GET | `/setup` | 登录 | 配置指引（用户标识符、端点） |
| GET | `/api/devices` | 登录 | 页面轮询用的 JSON |
| GET | `/healthz` | 无 | 健康检查 |

## 1. 获取任务

### 请求

```http
POST /maa/getTask
Content-Type: application/json

{
  "user": "用户在网页上拿到的 user_key",
  "device": "MAA 自动生成的设备标识符"
}
```

### 处理流程

1. 用 `user` 查 `users.user_key`，查不到直接 `401`（MAA 会提示连接测试失败）。
2. 用 `(user_id, device)` 找 `devices`，没有就新建一条，并刷新 `last_seen_at`。
   —— 这一步同时完成了「新实例自动登记」，所以用户不需要在网页上手动填设备 ID。
3. 取出该设备所有 `status = pending` 的任务，按创建时间排序，最多 20 条。
4. 把这些任务标记为 `delivered` 并记录 `delivered_at`。

### 响应

```json
{
  "tasks": [
    { "id": "f94fac9e-ecae-45de-a6ba-fc068648bbf2", "type": "LinkStart" },
    { "id": "1e5c…", "type": "Settings-Stage1", "params": "1-7" }
  ]
}
```

队列为空时返回 `{"tasks": []}`。

## 2. 回报结果

```http
POST /maa/reportStatus
Content-Type: application/json

{
  "user": "…",
  "device": "…",
  "task": "任务 id",
  "status": "SUCCESS",
  "payload": "截图任务的 Base64 图片，其它任务为空字符串"
}
```

处理流程：

1. 校验 `user` 与 `device`（设备必须属于该用户），否则 `401` / `404`。
2. 任务必须存在且属于该设备，否则 `404`。
3. 任务已经结束（重复回报）时直接返回 `{"ok": true, "duplicated": true}`，不覆盖结果。
4. `status` 归一化为大写，等于 `SUCCESS` 记为成功，其它值记为失败并把 `payload` 前 2000 字存进 `error_message`。
5. 截图类任务（`CaptureImage` / `CaptureImageNow`）把 `payload` 解码后写入 `data/screenshots/{task_id}.png`，
   支持裸 Base64 和 `data:image/png;base64,…` 两种形式。

## 任务状态机

```
pending ──(MAA 轮询取走)──▶ delivered ──(收到回报)──▶ success / failed
                                    └──(15 分钟没回报)──▶ timeout
```

- **只下发一次**：`delivered` 之后不会再返回给 MAA。原因是 MAA 重启后会忘记「已执行过的 id」，
  如果无限重发，一条 `LinkStart` 可能被重复执行。
- **超时回收**：每次轮询时顺带把超过 15 分钟没有回报的 `delivered` 任务标记为 `timeout`，
  避免队列里永远挂着一条僵尸任务。想重试就再点一次。

## 支持的任务类型

| type | 说明 | 需要 params |
| --- | --- | --- |
| `LinkStart` | 一键长草（按 MAA 主界面勾选执行） | 否 |
| `LinkStart-Base` | 基建换班 | 否 |
| `LinkStart-WakeUp` | 开始唤醒 | 否 |
| `LinkStart-Combat` | 刷理智 | 否 |
| `LinkStart-Recruiting` | 自动公招 | 否 |
| `LinkStart-Mall` | 信用购物 | 否 |
| `LinkStart-Mission` | 领取奖励 | 否 |
| `LinkStart-AutoRoguelike` | 自动肉鸽 | 否 |
| `Toolbox-GachaOnce` / `Toolbox-GachaTenTimes` | 抽卡 | 否 |
| `Toolbox-Reclamation` | 生息演算 | 否 |
| `Settings-ConnectAddress` | 修改连接地址 | 是，如 `127.0.0.1:16384` |
| `Settings-Stage1` | 修改刷关关卡 | 是，如 `1-7` |
| `CaptureImage` | 截图（排在队列后面执行） | 否 |
| `CaptureImageNow` | 截图（立即执行） | 否 |
| `StopTask` | 停止当前任务 | 否 |
| `HeartBeat` | 心跳，payload 返回当前正在执行的任务 id | 否 |

> `Settings-*` 仍然按顺序执行，不会插队；`CaptureImageNow` / `StopTask` / `HeartBeat` 属于「立即执行」类。

## 用 curl 手动调试

```bash
KEY="你的用户标识符"
BASE="http://127.0.0.1:8000"

# 1. 模拟一次轮询（顺便登记设备）
curl -s -X POST "$BASE/maa/getTask" \
  -H 'Content-Type: application/json' \
  -d "{\"user\":\"$KEY\",\"device\":\"debug-device\"}"

# 2. 模拟回报
curl -s -X POST "$BASE/maa/reportStatus" \
  -H 'Content-Type: application/json' \
  -d "{\"user\":\"$KEY\",\"device\":\"debug-device\",\"task\":\"<任务 id>\",\"status\":\"SUCCESS\",\"payload\":\"\"}"
```

网页上给 `debug-device` 下发任务后，第一条命令就能把它取出来，方便验证反向代理和鉴权是否正常。

## 安全模型

- MAA 端点是**匿名**的，协议本身没有签名机制，因此：
  - `user_key` 使用 `secrets.token_urlsafe(24)`（约 192 bit）生成，等同一把口令；
  - 必须走 HTTPS，否则 `user_key` 会明文飞过网络；
  - 泄露后在数据库里换掉 `user_key` 即可吊销所有旧 MAA 的访问。
- 截图文件按任务 id 命名，只能通过已登录的页面访问，路径做了目录穿越校验。
- 网页侧：`bcrypt` 存密码、会话 Cookie 带 `SameSite=Lax`、所有写操作校验 CSRF token。
