# 运行与维护

## 定时任务

`.github/workflows/checkin.yml` 提供两种触发方式：

| 触发方式 | 配置 |
|----------|------|
| 定时运行 | UTC 00:10，即北京时间约 08:10 |
| 手动运行 | GitHub Actions `workflow_dispatch` |

GitHub schedule 可能延迟。公开仓库长期没有仓库活动时，GitHub 可能停用 scheduled workflows；计划任务自身的运行不计为仓库活动。`.github/workflows/keepalive.yml` 仅用于定期检查计划任务状态，维护者仍需关注 Actions 是否保持启用。

## 一次运行的阶段

1. 安装 Python 依赖和 Playwright Chromium。
2. 从 Worker 拉取启用账号。
3. 逐个获取用户信息并执行签到。
4. 查询成功账号的本月签到统计。
5. 发送可选钉钉通知。
6. 将运行结果上报 Worker。

## 健康检查

生产部署后访问：

```text
https://<WORKER_HOST>/api/health
```

`database: connected` 表示 D1 可查询。HTTP 503 响应中的 `missing` 数组用于定位缺失的 Binding 或 Secret。

## 账号健康状态

Worker 根据每次 Runner 上报更新：

- 成功后将 `failure_count` 归零，并设置 `last_status=success`。
- 失败后增加 `failure_count`，并设置 `last_status=failed`。
- 更新凭据后清空连续失败次数和最近状态。
- 停用账号后 Runner 配置接口不再返回该账号。

## 升级部署

Cloudflare Workers Builds 连接 `main` 分支后，每次推送都会执行 `worker/package.json` 中的 `wrangler deploy`。

`worker/wrangler.toml` 仅声明 `Check` Binding。远端已存在同名 D1 Binding 时，Wrangler 继承原数据库；远端缺少该 Binding 时自动配置新数据库。

升级后执行以下检查：

1. Cloudflare Deployment 状态为成功。
2. Worker Bindings 中存在 D1 `Check`。
3. `/api/health` 返回成功。
4. Dashboard 可显示原账号和运行历史。
5. 手动 Actions 运行可以获取账号并上报结果。

## 常见故障定位

| 现象 | 优先检查 |
|------|----------|
| `/api/health` 返回 503 | `missing` 数组和 Worker Bindings |
| Dashboard 口令错误 | `DASHBOARD_PASSWORD` |
| Dashboard 登录后立即过期 | `SESSION_TTL_SECONDS` 和 D1 `sessions` |
| Runner 未授权 | 两端 Runner Token 是否一致 |
| Runner 获取 0 个账号 | Dashboard 中是否存在启用账号 |
| 账号认证失败 | Session 与 `new-api-user` 是否匹配 |
| Cloudflare 挑战失败 | Playwright 安装、目标站点策略、Cookie 有效期 |
| D1 解密错误 | `DATA_ENCRYPTION_KEY` 是否发生变化 |
| 定时任务未触发 | Workflow 启用状态和最近仓库活动 |

## 数据保留

项目当前保留全部账号、运行摘要和账号级结果。Dashboard 查询最近 30 次运行，历史数据仍保存在 D1。需要长期运行时，应根据 D1 配额制定归档或清理策略。

## 恢复原则

- Cloudflare 构建失败时继续使用上一份成功部署。
- D1 与 Worker 代码部署相互独立，代码更新不会清空表数据。
- `DATA_ENCRYPTION_KEY` 是账号密文恢复的必要条件。
- Runner Token 轮换需要同步更新 Cloudflare 与 GitHub。
