# Check Console 开发文档

本目录记录 Check Console 的实现架构、接口契约和开发流程。用户部署操作以仓库根目录的指南为准。

## 文档索引

| 文档 | 内容 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系统边界、组件职责、数据流与数据模型 |
| [INTERFACES.md](INTERFACES.md) | Worker HTTP API、鉴权和请求响应字段 |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | 本地开发、验证命令和修改约定 |
| [OPERATIONS.md](OPERATIONS.md) | 运行机制、可观测性、升级和故障定位 |

## 用户文档

| 文档 | 内容 |
|------|------|
| [README.md](../README.md) | 项目概览与快速部署 |
| [FIRST_RUN.md](../FIRST_RUN.md) | 账号录入与首次签到 |
| [WORKER_DEPLOYMENT.md](../WORKER_DEPLOYMENT.md) | 完整部署与排障 |
| [SECURITY.md](../SECURITY.md) | 凭据、加密和安全边界 |

## 源码入口

| 模块 | 文件 |
|------|------|
| GitHub Actions Runner | `checkin.py` |
| Cloudflare 检测与浏览器回退 | `cf_bypass.py` |
| 钉钉通知 | `dingtalk_notifier.py` |
| Worker API | `worker/src/index.js` |
| Dashboard | `worker/public/index.html` |
| D1 Schema | `worker/schema.sql` |
| Worker 配置 | `worker/wrangler.toml` |

## 文档维护原则

1. API 行为以 `worker/src/index.js` 为准。
2. Runner 行为以 `checkin.py` 为准。
3. 部署配置以 `worker/wrangler.toml` 和 GitHub Workflows 为准。
4. 示例统一使用虚构域名和占位凭据。
5. 功能变更应同步更新 README、相关指南和本目录对应页面。
