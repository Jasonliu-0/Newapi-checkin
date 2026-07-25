# 开发者指南

## 环境要求

- Node.js 22+
- Wrangler 4+
- Python 3.11+
- Chromium，由 Playwright 管理

## Worker 本地开发

准备本地变量：

```bash
cd worker
cp .dev.vars.example .dev.vars
```

编辑 `.dev.vars`，使用专门的本地测试值。随后安装依赖并启动：

```bash
npm install
npm run db:init:local
npm run dev
```

本地地址默认为 `http://127.0.0.1:8787`。

## Runner 本地开发

安装 Python 依赖：

```bash
pip install -r requirements.txt
playwright install chromium
```

连接本地 Worker：

```bash
export CHECKIN_WORKER_URL=http://127.0.0.1:8787
export CHECKIN_RUNNER_TOKEN=<LOCAL_RUNNER_TOKEN>
python3 checkin.py
```

## 配置优先级

Runner 按以下顺序加载账号：

1. `CHECKIN_WORKER_URL` 与 `CHECKIN_RUNNER_TOKEN`。
2. `CONFIG_URL` 与可选 `CONFIG_AUTH`。
3. `NEWAPI_ACCOUNTS`。

Worker 模式是当前推荐路径，其余配置用于兼容已有部署。

## 常用验证

Python 语法检查：

```bash
python3 -m py_compile checkin.py cf_bypass.py dingtalk_notifier.py
```

Python 回归测试：

```bash
python3 -B -m unittest discover -v
```

Worker 语法检查：

```bash
node --check worker/src/index.js
```

Wrangler 配置和打包检查：

```bash
cd worker
wrangler deploy --dry-run
```

Git 补丁格式检查：

```bash
git diff --check
```

`tests/` 当前覆盖 Cookie 域限制、账号输入校验、签到端点回退和 Cloudflare 页面识别。涉及鉴权或 D1 写入的改动还应补充对应测试后再扩展行为。

## 修改检查清单

### Worker API

1. 保持 Dashboard 与 Runner 鉴权边界。
2. 检查所有 Dashboard 响应中的敏感字段。
3. 对 D1 修改使用参数绑定。
4. 保持 `ensureTables()` 与 `worker/schema.sql` 一致。
5. 同步更新 `INTERFACES.md`。

### Runner

1. 保持日志中的 URL、用户 ID 和用户名脱敏。
2. 为网络请求设置超时。
3. 保持 `/api/user/sign_in` 与旧端点回退顺序。
4. 将认证失败映射为 `session_expired`。
5. 保持结果上报失败与签到结果解耦。

### Dashboard

1. 使用同源相对 `/api` 路径。
2. 保持 401 自动返回登录页。
3. 避免在 DOM、日志或本地存储中保存账号 Session。
4. 检查桌面和移动端布局。

## 兼容工具

| 文件 | 用途 | 注意事项 |
|------|------|----------|
| `config_helper.py` | 生成旧版 `NEWAPI_ACCOUNTS` | 终端输出包含完整账号配置 |
| `test_checkin.py` | 测试单个账号 | 使用真实凭据时保护终端记录 |
| `debug_session.py` | 调试 Session 编码 | 输出可能包含敏感会话内容 |

## 文档同步

用户流程变化时更新 `README.md`、`FIRST_RUN.md` 或 `WORKER_DEPLOYMENT.md`。接口和架构变化时同步更新 `docs/`。安全边界变化时更新 `SECURITY.md`。
