# 安全说明

本文说明 Check Console 的凭据边界、数据保护方式和安全操作要求。项目会处理 NewAPI Session 与自动化执行 Token，部署者应将 Cloudflare Dashboard 和 GitHub Secrets 作为唯一的生产凭据入口。

## 敏感信息分类

| 信息 | 敏感级别 | 存储位置 | 泄露影响 |
|------|----------|----------|----------|
| NewAPI `session` | 高 | D1 加密字段 | 可能导致账号会话被冒用 |
| `cf_clearance` | 高 | D1 加密字段 | 可能暴露浏览器验证状态 |
| `DATA_ENCRYPTION_KEY` | 高 | Cloudflare Secret | 可用于解密 D1 中的账号配置 |
| `RUNNER_TOKEN` | 高 | Cloudflare Secret、GitHub Secret | 可读取 Runner 配置并上报结果 |
| `DASHBOARD_PASSWORD` | 高 | Cloudflare Secret | 可登录管理控制台 |
| Dashboard Token | 高 | 浏览器 `localStorage`、D1 哈希 | 可在有效期内调用管理 API |
| D1 Database ID | 低 | Cloudflare Dashboard | 资源标识，不提供独立访问权限 |

## 数据保护

- Worker 使用 Web Crypto API 的 AES-GCM 加密账号运行配置。
- `DATA_ENCRYPTION_KEY` 经 SHA-256 派生为 256 位 AES 密钥。
- 每次加密使用独立的 12 字节随机 IV。
- D1 的 `accounts.secret` 保存 URL、Session、用户 ID和可选 `cf_clearance` 的密文。
- Dashboard Token 仅以 SHA-256 哈希形式写入 D1。
- Dashboard API 只返回账号名称、站点 Origin、状态和运行结果。
- Runner API 使用独立 Bearer Token，并仅向执行器返回启用账号。

## 凭据配置

生产凭据应配置在以下位置：

| 平台 | 配置项 |
|------|--------|
| Cloudflare Worker Secrets | `DASHBOARD_PASSWORD`、`RUNNER_TOKEN`、`DATA_ENCRYPTION_KEY` |
| GitHub Actions Secrets | `CHECKIN_WORKER_URL`、`CHECKIN_RUNNER_TOKEN`、可选钉钉变量 |
| 本地开发 | `worker/.dev.vars` |

仓库示例、Issue、Actions 日志、截图和聊天记录统一使用 `<PLACEHOLDER>`。`.env`、`worker/.dev.vars` 和常见账号配置文件已加入 `.gitignore`。

## 轮换策略

### Dashboard Password

在 Cloudflare Dashboard 更新 `DASHBOARD_PASSWORD` 后重新部署。已有 Dashboard Token 会持续到自身过期，可通过清理 D1 `sessions` 表立即结束全部控制台会话。

### Runner Token

生成新值后同步更新：

1. Cloudflare Secret `RUNNER_TOKEN`。
2. GitHub Secret `CHECKIN_RUNNER_TOKEN`。
3. 手动运行一次签到工作流验证连接。

### Data Encryption Key

该密钥与 D1 中已有密文强绑定。轮换流程为：记录现有账号列表、更新密钥、重新录入每个账号凭据。旧密钥应保留到迁移验收完成。

### NewAPI Session

账号出现认证失败时，在目标站点重新登录，再通过控制台“更新凭据”提交新的 Session 和用户 ID。

## 浏览器安全

- 在受信任设备访问 Worker 控制台。
- 共享设备使用结束后点击退出，并清理站点数据。
- Worker 自定义域可结合 Cloudflare Access 增加身份认证层。
- Dashboard Token 存储在浏览器 `localStorage`，同源脚本具有读取权限。

## 日志与调试

`checkin.py` 默认对站点 URL、用户 ID 和用户名做脱敏处理。排障时仍应检查第三方响应内容，避免服务端错误消息携带账号信息。

以下兼容工具仅适合本地临时排障：

| 工具 | 风险 |
|------|------|
| `debug_session.py` | 会解析并打印 Session 内容 |
| `config_helper.py` | 会在终端输出完整旧版账号配置 |
| `test_checkin.py` | 会直接使用传入的账号凭据访问站点 |

这些工具应在受控终端运行，输出文件和终端历史应按敏感数据处理。

## Cloudflare 挑战

Playwright 回退流程用于账号所有者访问其已授权使用的站点。目标站点策略、浏览器指纹、IP 和 Cookie 有效期会影响结果。部署者应遵守目标站点服务条款，并接受挑战失败作为正常运行结果。

## 安全问题反馈

发现可能泄露 Session、Token 或密钥的问题时，请使用 GitHub Security Advisory 私下报告，并在报告中使用脱敏日志和最小复现信息。
