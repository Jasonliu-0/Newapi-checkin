# HTTP 接口

Worker 根地址同时提供静态 Dashboard 和 `/api/*` JSON API。所有 JSON 响应使用 UTF-8，并设置 `Cache-Control: no-store`。

## 鉴权

受保护接口使用 Bearer Token：

```http
Authorization: Bearer <TOKEN>
```

Dashboard API 使用登录接口签发的短期 Token。Runner API 使用 Cloudflare Secret `RUNNER_TOKEN`。

## 健康检查

### GET /api/health

鉴权：无。

成功响应：

```json
{
  "ok": true,
  "service": "newapi-checkin-worker",
  "database": "connected",
  "time": "2026-01-01T00:00:00.000Z"
}
```

配置缺失时返回 HTTP 503，`missing` 可能包含 `Check`、`DASHBOARD_PASSWORD`、`RUNNER_TOKEN` 或 `DATA_ENCRYPTION_KEY`。

## 登录接口

### POST /api/auth/login

请求：

```json
{
  "password": "<DASHBOARD_PASSWORD>"
}
```

成功响应：

```json
{
  "token": "<DASHBOARD_TOKEN>",
  "expires_at": "2026-01-02T00:00:00.000Z"
}
```

### POST /api/auth/logout

使用 Dashboard Bearer Token 调用。Worker 删除对应的服务端会话，响应为 `{"ok": true}`。

## Dashboard API

以下接口均要求 Dashboard Bearer Token。

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/dashboard/summary` | 最近运行与账号状态 |
| `GET` | `/api/dashboard/runs` | 最近 30 次运行 |
| `GET` | `/api/dashboard/runs/:id` | 指定运行和账号级结果 |
| `GET` | `/api/dashboard/accounts` | 脱敏账号列表 |
| `POST` | `/api/dashboard/accounts` | 添加账号 |
| `PATCH` | `/api/dashboard/accounts/:id` | 更新凭据或启用状态 |

### 添加账号

```json
{
  "name": "主力站",
  "url": "https://api.example.com",
  "session": "<SESSION_VALUE>",
  "user_id": "12345",
  "cf_clearance": "<OPTIONAL_CLEARANCE_VALUE>"
}
```

`name`、`url`、`session` 和 `user_id` 为必填字段。`url` 必须为不含嵌入式凭据的 HTTPS 地址，Worker 将其规范化为 Origin，并加密完整运行配置。

### 更新启用状态

```json
{
  "enabled": false
}
```

### 更新凭据

```json
{
  "name": "主力站",
  "url": "https://api.example.com",
  "session": "<NEW_SESSION_VALUE>",
  "user_id": "12345",
  "cf_clearance": ""
}
```

更新凭据后，Worker 会清零连续失败次数和最近状态。

## Runner API

以下接口均要求 Runner Bearer Token。

### GET /api/runner/config

返回所有启用账号的运行配置：

```json
{
  "accounts": [
    {
      "name": "主力站",
      "account_id": 1,
      "url": "https://api.example.com",
      "session": "<SESSION_VALUE>",
      "user_id": "12345",
      "cf_clearance": "<OPTIONAL_CLEARANCE_VALUE>"
    }
  ]
}
```

### POST /api/runner/report

```json
{
  "execution_time": "2026-01-01 08:10:00",
  "total": 1,
  "success_count": 1,
  "fail_count": 0,
  "results": [
    {
      "account_id": 1,
      "name": "主力站",
      "success": true,
      "message": "签到成功",
      "quota_awarded": 1000,
      "checkin_count": 12,
      "session_expired": false
    }
  ]
}
```

单次最多上报 40 个账号结果，控制台也限制最多启用 40 个账号。Worker 根据 `results` 重新计算总数、成功数和失败数，并通过 D1 batch 提交运行记录、账号明细和状态更新。

## 错误响应

错误统一返回 JSON：

```json
{
  "error": "错误说明"
}
```

| 状态码 | 含义 |
|--------|------|
| `400` | 请求字段或 JSON 格式错误 |
| `401` | Token 无效、访问口令错误或登录过期 |
| `404` | 路由或账号不存在 |
| `500` | Worker、加密或数据库内部错误 |
| `503` | 必要 Binding 或 Secret 缺失 |
