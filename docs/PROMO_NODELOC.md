# NodeLoc 社区分享稿

> 可直接复制到 [NodeLoc](https://www.nodeloc.com/) 发帖。  
> 发帖前建议配 1～2 张控制台截图，注意打码 Session、Token 等敏感信息。

---

## 推荐标题

```text
开源自用：NewAPI 多账号自动签到控制台（CF Worker + D1）
```

---

## 正文

```markdown
## 先说结论

做了一个 **NewAPI / OneAPI 多账号自动签到控制台**，自用了一段时间，开源出来。

仓库：  
https://github.com/zhikanyeye/Newapi-checkin

MIT 协议。  
基于原作者 Jasonliu-0 的签到逻辑改造，加了网页控制台、加密存储和结果看板。

---

## 能干什么

- 多账号管理：添加、更新、启用、停用
- 每天自动签到：GitHub Actions 定时跑
- 网页看板：看成功失败、连续失败、最近 30 次记录
- Session 加密存 D1，页面不回显明文
- 支持钉钉通知（可选）

不用自己挂服务器，不用 GitHub Pages。  
Cloudflare Worker 一个地址，同时提供页面和 API。

---

## 怎么跑起来的

```text
浏览器控制台
      ↓
Cloudflare Worker  ←→  D1（加密账号 + 历史）
      ↑
GitHub Actions 每天签到
      ↓
NewAPI 各站点
```

一句话：  
**Worker 管配置和结果，Actions 只负责执行。**

---

## 部署大概四步

1. 把仓库接到 Cloudflare Workers Builds  
   - Root directory：`worker`  
   - Deploy command：`npm run deploy`
2. 在 Worker 填 3 个 Secret  
   - `DASHBOARD_PASSWORD`  
   - `RUNNER_TOKEN`  
   - `DATA_ENCRYPTION_KEY`
3. 在 GitHub Actions 填 2 个 Secret  
   - `CHECKIN_WORKER_URL`  
   - `CHECKIN_RUNNER_TOKEN`（和 `RUNNER_TOKEN` 同值）
4. 控制台录入账号，手动跑一次 workflow，看结果是否回写

详细文档：

- 快速开始：`README.md`
- 首次联调：`FIRST_RUN.md`
- 完整部署：`WORKER_DEPLOYMENT.md`
- 安全说明：`SECURITY.md`

---

## 账号要填什么

| 字段 | 说明 |
|------|------|
| 备注名称 | 自己认得就行 |
| 用户 ID | 浏览器 Network 请求头 `new-api-user` |
| 站点地址 | 根地址，如 `https://api.example.com` |
| Session | Cookie 里 `session` 的 Value |
| cf_clearance | 一般留空 |

注意：

- Session 只贴 Value，别带 `session=`
- 用户 ID 必填
- 站点地址别带 `/console/...`

---

## 几个实际体验

**方便的地方**

- 账号不用再塞 GitHub Secrets
- 过期了直接在网页更新凭据
- 结果回控制台，不用翻日志
- 仓库不写 D1 database_id，别人复制也方便

**仍要注意的**

- Session 会过期，需要手动更新
- 有 Cloudflare 挑战的站，不保证每次过
- GitHub 定时任务可能延迟
- 不同 NewAPI 衍生站接口可能有差异

---

## 适合谁

适合：

- 手上有多个 NewAPI / OneAPI 兼容站账号
- 想每天自动签到
- 能接受 Cloudflare + GitHub 这套免费/低成本组合

不适合：

- 想完全零维护
- 想一键过所有站点风控
- 不想碰基础配置

---

## 安全提醒

- 三个 Secret 用不同随机值
- 别把 Session / Token 发到群里、Issue、截图
- `DATA_ENCRYPTION_KEY` 自己备份，丢了旧账号密文解不开
- 只建议用在自己有权限的账号上

---

## 链接

GitHub：  
https://github.com/zhikanyeye/Newapi-checkin

如果有人部署成功，欢迎回帖说下：

- 用了几个号
- 有没有卡 CF
- 整体稳不稳

有问题也可以在仓库开 Issue。自用项目，修 bug 看时间，别按商业支持预期。
```
