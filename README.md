# NewAPI 自动签到

基于 HTTP 直连的 NewAPI 自动签到脚本，支持多账号、GitHub Actions 定时执行。

## ✨ 功能特性

- ✅ 支持单账号/多账号签到
- ✅ **支持多个不同网站**（只要是基于 NewAPI 搭建的站点）
- ✅ HTTP 直连，无需浏览器
- ✅ GitHub Actions 自动化执行
- ✅ 详细的签到日志输出
- ✅ 错误处理和超时控制
- ✅ 支持手动触发和定时任务
- ✅ **钉钉通知**（签到完成后自动推送结果）
- ✅ **邮件通知**（支持 SMTP 发送签到报告）
- ✅ **Server酱推送**（支持 ServerChan 微信推送）
- ✅ **Session 自动续期**（过期后自动使用配置的账号密码重新登录，新 session 自动回写 .env）
- ✅ **重复签到检测**（已签到自动标记成功，避免误报）
- ✅ **工作流保活**（防止 GitHub Actions 自动禁用）
- ✅ **请求限流处理**（登录接口返回 429 时友好跳过，不会直接报错）
- ✅ **哈基米中转站专属抽奖**（lanxiu.cc 站点签到后自动抽取额度，每日 2 次，仅本地运行）
- ✅ **维云中转站专属翻卡**（vsllm.com 站点签到后自动翻卡，每日 3 次，本地和 GHA 均可运行）
- ✅ **系统访问令牌认证**（access_token 走 Authorization 头，不依赖 session，永不过期烦恼）
- ✅ **Cloudflare 自动应对**（网络层挑战用浏览器过检，已实测 GitHub Actions 数据中心 IP 可通过）
- ✅ **Turnstile 人机验证自动求解**（真实 Chrome 渲染组件并模拟点击，token 自动携带）
- ✅ **PoW 工作量证明自动解算**（new-api 新版防滥用机制，SHA-256 前导零比特本地解算）
- ✅ **液态玻璃双主题配置页**（浅色/深色一键切换，移动端自适应）

## 🛠️ 配置工具（推荐）

为了让配置更简单，我们提供了两个便捷工具：

### 🌐 方式 1：网页配置生成器（最简单）

**在线使用（推荐）：**

如果你的仓库启用了 GitHub Pages，可以直接访问：
```
https://你的用户名.github.io/Newapi-checkin/config_generator.html
```

**启用 GitHub Pages 的方法：**
1. 进入仓库 `Settings` → `Pages`
2. 在 `Source` 下选择 `main` 分支
3. 点击 `Save`
4. 等待几分钟后，访问上面的链接

**本地使用：**
1. 下载 `config_generator.html` 文件到本地
2. 双击文件，用浏览器打开
3. 填写站点 URL、Session Cookie 和备注名称
4. 点击"生成配置"按钮
5. 一键复制生成的配置

**特点：**
- 📱 支持移动端和桌面端
- ✨ 可视化界面，无需编写代码
- 🎯 自动格式化，避免语法错误
- 📋 一键复制到剪贴板
- 🌐 可在线访问，无需安装任何软件
- 💾 **支持本地存储**，下次打开自动加载配置

### 💻 方式 2：命令行配置助手

```bash
python config_helper.py
```

**功能：**
- ✅ 交互式问答，逐步引导配置
- ✅ 自动测试账号有效性
- ✅ 支持生成 JSON 和简单格式
- ✅ 自动保存到文件

**使用示例：**
```
--- 配置第 1 个账号 ---
站点 URL（如 https://xxx.xxx）: https://xxx.xxx
Session Cookie: MTc2NzQxMzYzM3xEWDhF...
备注名称（可选，便于识别） [站点1]: 主站
是否测试此账号配置 (Y/n): y
正在测试...
  ✅ 测试成功！用户名: xxx_xxx
✅ 第 1 个账号添加成功

是否继续添加账号 (y/N): n
```

---

## 🚀 快速开始

### 📝 配置流程图

```
1. 使用配置工具生成配置
   ↓
   [网页工具] → 填写表单 → 生成配置 → 复制
   或
   [命令行工具] → 交互式问答 → 自动测试 → 保存文件
   ↓
2. 添加到 GitHub Secrets
   ↓
3. 启用 GitHub Actions
   ↓
4. 每天自动签到 ✅
```

### 方式一：GitHub Actions（推荐）

#### 1. Fork 本仓库

点击右上角 `Fork` 按钮，将本仓库 Fork 到你的账号下。

#### 1.5. 启用 GitHub Pages（使用网页工具必需）

**重要：** 如果你想使用在线网页配置工具，需要先启用 GitHub Pages：

1. 进入你 Fork 的仓库
2. 点击 `Settings` → `Pages`
3. 在 `Source` 下选择 `Deploy from a branch`
4. 选择 `main` 分支，文件夹选择 `/ (root)`
5. 点击 `Save`
6. 等待 1-2 分钟，页面会显示访问链接

**访问你的配置工具：**
```
https://你的用户名.github.io/Newapi-checkin/
```

或直接访问配置生成器：
```
https://你的用户名.github.io/Newapi-checkin/config_generator.html
```

> 💡 **提示：** 将上面的"你的用户名"替换为你的 GitHub 用户名

#### 2. 配置 Secrets

进入你 Fork 的仓库，依次点击：`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

添加名为 `NEWAPI_ACCOUNTS` 的 Secret。

> 💡 **推荐使用配置工具生成配置**（见上方"配置工具"章节），也可以按以下格式手动配置：

**单账号格式：**
```
https://your-domain.com#your_session_cookie
```

**多账号/多网站格式（用逗号分隔）：**
```
https://site1.com#session1,https://site2.com#session2,https://site3.com#session3
```

**实际示例（多个不同的 NewAPI 站点）：**
```
https://api.example1.com#MTc2NzQx...,https://api.example2.com#QVFMXzJh...,https://api.example3.com#RFhFN0FB...
```

**JSON 格式（推荐，支持备注和更好的可读性）：**
```json
[
  {
    "url": "https://api.example.com",
    "session": "MTc2NzQxMzYzM3xEWDhFQVFMX2dBQUJFQUVRQUFE...",
    "user_id": "123",
    "name": "主力站"
  },
  {
    "url": "https://api2.example.com",
    "session": "QVFMXzJhYWJFRUFRQUFEX3dfLUFBQVlHYzNS...",
    "user_id": "456",
    "name": "备用站"
  },
  {
    "url": "https://api3.example.com",
    "session": "RFhFN0FBQkVBRVFBQUQzd19fQUFBWUdjM1J5...",
    "user_id": "789",
    "name": "测试站"
  }
]
```

#### 3. 启用 GitHub Actions

进入仓库的 `Actions` 页面，点击 `I understand my workflows, go ahead and enable them` 启用工作流。

#### 4. 测试运行

在 `Actions` 页面，选择 `NewAPI 自动签到` 工作流，点击 `Run workflow` 按钮手动触发一次测试。

#### 5. 定时执行

工作流默认每天 **北京时间 8:10** 自动执行签到，无需手动操作。

---

### 方式二：本地运行

#### 1. 克隆仓库

```bash
git clone https://github.com/Jasonliu-0/Newapi-checkin.git
cd Newapi-checkin
```

#### 2. 安装依赖

```bash
pip install -r requirements.txt
```

#### 3. 配置环境变量

**Linux/macOS：**
```bash
export NEWAPI_ACCOUNTS="https://your-domain.com#your_session_cookie"
```

**Windows PowerShell：**
```powershell
$env:NEWAPI_ACCOUNTS="https://your-domain.com#your_session_cookie"
```

**Windows CMD：**
```cmd
set NEWAPI_ACCOUNTS=https://your-domain.com#your_session_cookie
```

#### 4. 运行脚本

```bash
python checkin.py
```

#### 5. 测试单个站点（可选）

在配置多个站点前，可以先用测试脚本验证单个站点：

```bash
python test_checkin.py <站点URL> <session值>
```

**示例：**
```bash
python test_checkin.py https://xxx.xxx MTc2NzQxMzYzM3xEWDhFQVFMX2...
```

测试脚本会验证：
1. Session 是否有效（获取用户信息）
2. 签到功能是否正常
3. 签到历史查询是否正常

---

## 🔑 获取 Session Cookie

### 方法一：浏览器开发者工具（推荐）

1. 打开 NewAPI 网站并登录
2. 按 `F12` 打开开发者工具
3. 切换到 `Network`（网络）标签
4. 刷新页面（`F5`）
5. 在请求列表中找到任意 API 请求
6. 点击该请求，查看 `Headers`（请求头）
7. 找到 `Cookie` 字段，复制其中 `session=` 后面的值

**示例：**
```
Cookie: session=MTc2NzQxMzYzM3xEWDhFQVFMX2...; cf_clearance=...
```

只需要复制 `session=` 和 `;` 之间的部分：
```
MTc2NzQxMzYzM3xEWDhFQVFMX2...
```

### 方法二：使用脚本提取

在浏览器控制台（Console）中运行：

```javascript
document.cookie.split('; ').find(row => row.startsWith('session=')).split('=')[1]
```

直接复制输出的值即可。

---

## 🎫 使用系统访问令牌（推荐，替代 Session）

站点开启 Cloudflare 防护或 Turnstile 人机验证时，**强烈推荐使用系统访问令牌**——通过 `Authorization` 请求头认证，不依赖 session cookie，且签到脚本会自动应对 CF 挑战与 Turnstile/PoW 验证。

### 获取方式

1. 浏览器登录站点
2. 点击右上角头像 → **个人设置**
3. 找到 **系统访问令牌** → 生成并复制
4. 注意：不是 `sk-` 开头的 API 密钥，两者不可混用

### 配置格式

JSON 格式中加入 `access_token` 字段（session 与令牌二选一，推荐令牌）：

```json
[
  {
    "url": "https://example.com",
    "session": "",
    "access_token": "你的系统访问令牌",
    "user_id": "123",
    "name": "站点备注"
  }
]
```

简单格式支持三段式：`https://example.com#session#access_token`

### 脚本自动应对的防护机制

| 防护 | 应对方式 |
| --- | --- |
| Cloudflare 网络层挑战（Just a moment） | 无头浏览器过检，失败自动切换真实 Chrome |
| Turnstile 人机验证 | 真实 Chrome 渲染组件并模拟点击，token 自动携带 |
| PoW 工作量证明（new-api 新版） | 本地解算 SHA-256 nonce（毫秒到数秒） |
| WAF 硬封禁（IP 段拉黑） | 无法技术破解，需更换出口 IP（本地可配置系统代理） |

> ⚠️ GitHub Actions 使用数据中心 IP，部分站点可能对其 WAF 策略更严格；本地运行可配合系统代理使用。

---

## ⚙️ 配置说明

### 定时执行时间

默认每天 **北京时间 8:10** 执行，如需修改，编辑 `.github/workflows/checkin.yml`：

```yaml
schedule:
  - cron: '10 0 * * *'  # UTC 0:10 = 北京时间 8:10
```

**常用时间对照：**
- `0 0 * * *` - 每天 UTC 0:00（北京时间 8:00）
- `30 1 * * *` - 每天 UTC 1:30（北京时间 9:30）
- `0 16 * * *` - 每天 UTC 16:00（北京时间 0:00）


### 🔔 通知配置（可选）

签到完成后自动发送通知，支持 **钉钉**、**邮件**、**Server酱** 三种推送方式。

---

#### 钉钉通知

##### 1. 创建钉钉机器人

1. 打开钉钉群 → **设置** → **智能群助手**
2. 点击 **添加机器人** → 选择 **自定义**
3. 设置机器人名称（如：签到通知）
4. 安全设置选择 **加签**（推荐）或 **自定义关键词**
5. 复制 **Webhook 地址** 和 **签名密钥**

##### 2. 添加 GitHub Secrets

| Secret 名称 | 说明 | 是否必须 |
|-------------|------|----------|
| `DINGTALK_WEBHOOK` | 钉钉机器人 Webhook URL | 是 |
| `DINGTALK_SECRET` | 加签密钥（以 SEC 开头） | 否（如开启加签则必须） |

---

#### 邮件通知

签到完成后通过 SMTP 发送签到报告到指定邮箱。

##### 添加 GitHub Secrets

| Secret 名称 | 说明 | 是否必须 |
|-------------|------|----------|
| `SMTP_HOST` | SMTP 服务器地址（如 `smtp.qq.com`） | 是 |
| `SMTP_PORT` | SMTP 端口（如 `465`） | 否（默认 465） |
| `SMTP_USER` | 发件邮箱地址 | 是 |
| `SMTP_PASS` | 邮箱授权码或密码 | 是 |
| `SMTP_TO` | 收件邮箱地址 | 是 |

> **提示：** 使用 QQ 邮箱等需开启 SMTP 服务并获取授权码，非登录密码。

---

#### Server酱推送

支持通过 [ServerChan](https://sct.ftqq.com/) 推送签到结果到微信。

##### 添加 GitHub Secrets

| Secret 名称 | 说明 | 是否必须 |
|-------------|------|----------|
| `SERVERCHAN_KEY` | ServerChan SendKey | 是 |

---

#### 通知内容示例

```
📋 NewAPI 签到报告
执行时间: 2026-01-08 08:10:00

✅ 成功 (2个)
| 账号 | 奖励 | 详情 | 抽奖 |
| 主力站 | +500K | 已签 15 天 | 🎉 小份额度 +5M |
| 备用站 | +100K | 已签 8 天 | 🎉 暴击 +10.00K |

汇总: 成功 2，失败 0
```

### Session 自动续期

脚本支持在 Session 过期时**自动使用配置的账号密码重新登录**，无需手动更新。

#### 配置方式

在 JSON 配置中为账号添加 `login_username` 和 `login_password` 字段：

```json
[
  {
    "url": "https://api.example.com",
    "session": "当前session值",
    "name": "主力站",
    "login_username": "your_username",
    "login_password": "your_password"
  }
]
```

> **提示：** 自动重新登录功能需要站点支持账号密码登录。登录成功后新 Session 会自动用于本次签到，无需额外操作。

#### .env 自动回写

本地运行（非 GitHub Actions）时，如果配置来自 `.env` 文件且登录产生了新 session，脚本会自动将更新后的 session **写回 `.env` 文件**，下次运行时直接使用新 session，无需手动复制粘贴。

触发条件（三项同时满足）：
1. 配置从 `.env` 文件的 `NEWAPI_ACCOUNTS=` 行加载
2. 至少有一个账号成功自动登录，session 产生变更
3. 非 GitHub Actions 环境运行

仅替换 `NEWAPI_ACCOUNTS=` 那一行，文件中的注释和其他配置原样保留。

---

### 🎲 中转站专属抽奖/翻卡

脚本内置了哈基米中转站和维云中转站的专属抽奖功能，签到后自动执行。

#### 哈基米中转站（lanxiu.cc）

签到成功后自动执行抽奖，每日最多 **2 次**。

**流程：** 获取绑定 key → 绑定 openid → 抽奖

绑定映射关系持久化到本地 `lottery_bindings.json` 文件，因此**仅在本地运行**时生效，GitHub Actions 环境自动跳过。

**配置：** 哈基米中转站的账号需要在 JSON 配置中包含 `login_username` 和 `login_password` 字段，用于自动续签 session。

**输出示例：**
```
  抽奖: 🎉 小份额度 +5M
```

#### 维云中转站（vsllm.com）

签到成功后自动翻卡，每日最多 **3 次**，**本地和 GitHub Actions 均可运行**（无需持久化映射）。

**流程：** 直接调用翻卡接口，无需绑定步骤。

**翻卡结果示例：**
```
  翻卡: 🎉 第1次 暴击 +10.00K
  翻卡: 🎉 第2次 小额惊喜 +1.00K
  翻卡: 🎉 第3次 幸运降临 +100.00K
```

#### 通知推送

抽奖/翻卡结果会一并纳入签到报告，在钉钉、邮件、ServerChan 的推送表格中显示为"抽奖"列：

```
| 账号 | 奖励 | 详情 | 抽奖 |
| 哈基米1558 | +2.50M | 已签 15 天 | 🎉 小份额度 +5M |
| 维云 | - | 已签 2 天 | 🎉 第1次 暴击 +10.00K / 🎉 第2次 小额惊喜 +1.00K |
```

冷却或已用完的情况显示 `⏭️ 今日已抽奖完成`。

---

### 💾 网页工具本地存储功能

网页配置生成器支持将配置保存到浏览器本地存储：

**功能说明：**
- ✅ **保存到本地**：填写完配置后，点击"💾 保存到本地"按钮
- ✅ **自动加载**：下次打开页面会提示恢复之前的配置
- ✅ **从本地加载**：点击"📂 从本地加载"按钮恢复配置
- ✅ **清除数据**：点击"🗑️ 清除本地数据"删除保存的配置

**安全提示：**
- ⚠️ 数据以**明文形式**存储在浏览器中
- ⚠️ 仅在**私人电脑**上使用本地存储功能
- ⚠️ 公共电脑请勿使用，用完记得清除
- ✅ 换电脑或换浏览器需要重新配置

**使用流程：**
```
1. 填写配置 → 2. 点击"保存到本地" → 3. 关闭页面
   ↓
下次打开页面
   ↓
4. 看到提示"发现本地保存的配置" → 5. 点击"从本地加载" → 6. 配置自动填充 ✅
```

### 账号配置格式详解

| 格式 | 说明 | 示例 |
|------|------|------|
| `URL#SESSION` | 单账号 | `https://api.example.com#MTc2NzQx...` |
| `URL1#SESSION1,URL2#SESSION2` | 多网站/多账号（逗号分隔） | `https://a.com#sess1,https://b.com#sess2` |
| JSON 数组 | 支持备注名称、用户ID和自动登录凭证（推荐） | 见下文 JSON 格式示例 |

### 多网站配置示例

脚本支持同时管理**多个不同的 NewAPI 站点**，每个站点独立签到。

**场景 1：管理 3 个不同的 NewAPI 站点**

假设你有以下站点的账号：
- `https://api.site1.com` - 主力站
- `https://api.site2.com` - 备用站
- `https://api.site3.com` - 测试站

配置方式（JSON 格式，推荐）：

```json
[
  {
    "url": "https://api.site1.com",
    "session": "你的site1的session值",
    "user_id": "123",
    "name": "主力站"
  },
  {
    "url": "https://api.site2.com",
    "session": "你的site2的session值",
    "user_id": "456",
    "name": "备用站"
  },
  {
    "url": "https://api.site3.com",
    "session": "你的site3的session值",
    "user_id": "789",
    "name": "测试站"
  }
]
```

**场景 2：同一个站点的多个账号**

如果你在同一个站点有多个账号，也可以这样配置：

```json
[
  {
    "url": "https://api.example.com",
    "session": "账号1的session",
    "name": "账号A"
  },
  {
    "url": "https://api.example.com",
    "session": "账号2的session",
    "name": "账号B"
  }
]
```

**场景 3：混合配置（多站点 + 多账号）**

```json
[
  {
    "url": "https://site1.com",
    "session": "site1_account1_session",
    "name": "站点1-账号A"
  },
  {
    "url": "https://site1.com",
    "session": "site1_account2_session",
    "name": "站点1-账号B"
  },
  {
    "url": "https://site2.com",
    "session": "site2_session",
    "name": "站点2"
  }
]
```

> **提示：** 每个站点的 Session Cookie 需要单独获取，请在对应站点登录后提取。

---

## 📋 运行日志示例

**多网站签到日志：**

```
==================================================
NewAPI 自动签到
执行时间: 2026-01-03 08:10:00
==================================================
共 3 个账号待签到

[1/3] 主力站
  站点: https://api.site1.com
  用户ID: 123
  用户: user_123
  结果: ✅ 签到成功
  日期: 2026-01-03
  奖励: +5.23M 额度 (5,230,000 tokens)
  统计: 本月已签 3 天，累计 15.67M 额度

[2/3] 备用站
  站点: https://api.site2.com
  用户ID: 456
  用户: user_456
  结果: ✅ 签到成功
  日期: 2026-01-03
  奖励: +2.78M 额度 (2,780,000 tokens)
  统计: 本月已签 3 天，累计 8.45M 额度

[3/3] 测试站
  站点: https://api.site3.com
  用户ID: 789
  用户: user_789
  结果: ✅ 签到成功
  日期: 2026-01-03
  奖励: +3.49M 额度 (3,487,044 tokens)
  统计: 本月已签 1 天，累计 3.49M 额度

==================================================
签到完成: 成功 3, 失败 0
==================================================
```

**日志说明：**
- ✅ **结果**：显示 API 返回的签到消息
- 📅 **日期**：本次签到的日期
- 🎁 **奖励**：本次获得的额度（格式化显示 + 原始值）
- 📊 **统计**：本月累计签到天数和总额度

---

## ❓ 常见问题

### Q1: 签到失败提示 "session 已过期"

**原因：** Session Cookie 过期或无效。

**解决：**
1. 自动续期：在 JSON 配置中配置 `username` 和 `password` 字段，脚本会自动重新登录（见"Session 自动续期"章节）
2. 手动更新：重新登录网站，获取新的 Session Cookie，更新 GitHub Secrets

### Q2: GitHub Actions 没有自动执行

**可能原因：**
1. 工作流未启用 - 进入 Actions 页面启用
2. 仓库长期无活动被暂停 - 手动触发一次即可恢复
3. Fork 的仓库默认禁用 Actions - 需要手动启用

### Q3: 如何查看执行日志？

进入仓库的 `Actions` 页面，点击对应的工作流运行记录，即可查看详细日志。

### Q4: 支持哪些 NewAPI 站点？

理论上支持所有基于 [New API](https://github.com/Calcium-Ion/new-api) 项目搭建的站点，只要 API 接口兼容即可。

### Q5: Session Cookie 多久会过期？

根据站点配置不同，通常为 **7-30 天**。建议每月更新一次，或在签到失败时及时更新。

### Q6: 每次签到获得的额度不一样？

**正常现象！** NewAPI 的签到奖励是随机的：
- 最小额度：通常 2.5M tokens
- 最大额度：通常 10M tokens
- 每次签到会在这个范围内随机分配

脚本会显示本次获得的具体额度和本月累计总额度。

### Q7: 脚本如何处理 new-api-user 请求头？

**自动处理！** 脚本会：
1. 调用 `/api/user/self` 获取用户信息
2. 自动提取用户ID
3. 将 `new-api-user: 用户ID` 添加到后续请求的请求头中
4. 无需手动配置，完全自动化

---

## 🔧 详细故障排除指南

### 1. Session 已过期

**错误信息：**
```
❌ 失败 - Session 可能已过期
```

**原因：**
- Session Cookie 已过期（通常 7-30 天）
- Session Cookie 复制不完整
- Session Cookie 格式错误

**解决方法：**

#### 步骤 1：使用调试模式查看详细信息
```bash
python test_checkin.py https://api.example.com "你的session" --verbose
```

#### 步骤 2：重新获取 Session Cookie

**方法 A：浏览器开发者工具（推荐）**

1. 打开 NewAPI 网站并登录
2. 按 `F12` 打开开发者工具
3. 切换到 `Application`（应用程序）或 `Storage`（存储）标签
4. 左侧找到 `Cookies` → 选择你的网站
5. 找到 `session` 这一行
6. 复制 `Value`（值）列的**完整内容**

**重要：** 确保复制完整，不要遗漏开头或结尾！

**方法 B：Network 标签法**

1. 打开网站并登录
2. 按 `F12` → `Network`（网络）标签
3. 刷新页面（`F5`）
4. 找到任意 API 请求
5. 查看 `Headers` → `Request Headers` → `Cookie`
6. 找到 `session=` 后面的值，复制到下一个分号之前

**方法 C：控制台脚本法**

1. 打开网站并登录
2. 按 `F12` → `Console`（控制台）
3. 输入以下代码并回车：
   ```javascript
   document.cookie.split('; ').find(row => row.startsWith('session=')).split('=')[1]
   ```
4. 复制输出的结果

#### 步骤 3：验证新的 Session

```bash
python test_checkin.py https://api.example.com "新的session" --verbose
```

如果成功，你会看到：
```
[1/3] 测试获取用户信息...
  [调试] HTTP 状态码: 200
  [调试] success 字段: True
✅ 成功
  用户名: xxx
  用户ID: 123
```

---

### 2. Session 复制不完整

**症状：**
- Session 长度异常短（少于 100 字符）
- 测试立即失败

**检查方法：**
```bash
python test_checkin.py https://api.example.com "你的session" --verbose
```

查看输出的 `Session 长度`，通常应该是 **200-500 字符**。

**正常示例：**
```
Session 长度: 384 字符
```

**异常示例：**
```
Session 长度: 50 字符  ← 太短，可能复制不完整
```

**解决：**
重新复制完整的 Session Cookie，确保：
- 从开头开始
- 到结尾结束
- 中间没有换行或空格

---

### 3. 网络连接问题

**错误信息：**
```
[错误] 网络请求失败: ...
```

**可能原因：**
1. 网站无法访问
2. 防火墙/代理阻止
3. DNS 解析失败

**解决方法：**

#### 检查网站是否可访问
```bash
# Windows
ping api.example.com

# 或使用浏览器直接访问
```

#### 检查代理设置
如果使用代理，需要设置环境变量：

```bash
# Linux/macOS
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080

# Windows CMD
set HTTP_PROXY=http://proxy.example.com:8080
set HTTPS_PROXY=http://proxy.example.com:8080

# Windows PowerShell
$env:HTTP_PROXY="http://proxy.example.com:8080"
$env:HTTPS_PROXY="http://proxy.example.com:8080"
```

---

### 4. JSON 解析失败

**错误信息：**
```
[错误] 响应解析失败: ...
```

**可能原因：**
- 网站返回了 HTML 错误页面（如 404、503）
- 网站维护中
- API 接口变更

**调试：**
```bash
python test_checkin.py https://api.example.com "你的session" --verbose
```

查看 `[调试] 原始响应:` 的内容，可能看到：
- HTML 错误页面
- 维护通知
- 其他非 JSON 内容

**解决：**
1. 等待网站恢复
2. 检查网站是否正常
3. 联系网站管理员

---

### 5. GitHub Actions 签到失败

**症状：**
- 本地测试成功
- GitHub Actions 运行失败

**可能原因：**
1. Secrets 配置错误
2. Session 已过期
3. GitHub 服务器网络问题

**排查步骤：**

#### 检查 Secrets 配置
1. 进入仓库 `Settings` → `Secrets and variables` → `Actions`
2. 确认 `NEWAPI_ACCOUNTS` 存在
3. 点击 `Update` 检查配置格式

#### 查看详细日志
1. 进入 `Actions` 页面
2. 点击失败的运行记录
3. 展开 `执行签到` 步骤
4. 查看详细错误信息

#### 手动触发测试
1. `Actions` → `NewAPI 自动签到`
2. `Run workflow` → `Run workflow`
3. 查看运行结果

---

### 6. 配置格式错误

**错误信息：**
```
❌ 账号配置解析失败
```

**常见错误：**

#### 错误 1：JSON 格式错误
```json
// ❌ 错误：缺少逗号
[
  {"url": "https://site1.com", "session": "sess1"}
  {"url": "https://site2.com", "session": "sess2"}
]

// ✅ 正确
[
  {"url": "https://site1.com", "session": "sess1"},
  {"url": "https://site2.com", "session": "sess2"}
]
```

#### 错误 2：引号问题
```json
// ❌ 错误：使用了中文引号
{"url": "https://site1.com", "session": "sess1"}

// ✅ 正确：使用英文引号
{"url": "https://site1.com", "session": "sess1"}
```

#### 错误 3：简单格式分隔符
```bash
# ❌ 错误：使用分号
https://site1.com;sess1,https://site2.com;sess2

# ✅ 正确：使用井号
https://site1.com#sess1,https://site2.com#sess2
```

**解决：**
使用配置工具生成配置，避免手动编写：
- 网页工具：`config_generator.html`
- 命令行工具：`python config_helper.py`

---

## 🔍 调试技巧

### 使用 --verbose 参数

启用详细调试信息：
```bash
python test_checkin.py https://api.example.com "你的session" --verbose
```

你会看到：
- HTTP 状态码
- API 响应内容
- 请求头信息
- 错误详情

### 检查 Session 格式

正确的 Session Cookie 特征：
- ✅ 长度：200-500 字符
- ✅ 格式：Base64 编码（字母、数字、`+`、`/`、`=`）
- ✅ 开头：通常是 `MTc...`
- ✅ 结尾：通常是 `...=` 或 `...==`

### 本地测试流程

1. **第一步：测试连接**
   ```bash
   ping api.example.com
   ```

2. **第二步：获取新 Session**
   - 登录网站
   - 使用开发者工具获取

3. **第三步：测试签到**
   ```bash
   python test_checkin.py https://api.example.com "新session" --verbose
   ```

4. **第四步：配置到生产**
   - 本地测试成功后
   - 更新 GitHub Secrets
   - 手动触发一次验证

---

## ⚠️ 注意事项

1. **保护隐私：** Session Cookie 相当于登录凭证，请妥善保管，不要泄露给他人
2. **定期更新：** Cookie 会过期，需要定期更新 Secrets 配置
3. **遵守规则：** 请遵守各站点的使用规则，合理使用自动签到功能
4. **Fork 仓库私有化：** 建议将 Fork 的仓库设为私有（Private），避免配置泄露
5. **测试后启用：** 首次配置完成后，先手动触发测试，确认无误后再依赖定时任务
6. **本地存储安全：** 浏览器本地存储是明文的，仅在私人电脑使用，公共电脑请勿使用

---

## 🔐 安全使用指南

### 数据存储方式对比

#### 1. GitHub Secrets（最安全，推荐）

**安全性：** ⭐⭐⭐⭐⭐

**优点：**
- ✅ 加密存储，GitHub 服务器加密保护
- ✅ 仅授权用户可见
- ✅ Actions 运行时自动注入，不会暴露
- ✅ 支持版本控制和审计
- ✅ 适合长期使用

**缺点：**
- ❌ 需要有 GitHub 账号
- ❌ 需要 Fork 仓库

**适用场景：**
- ✅ 日常自动签到（推荐）
- ✅ 长期使用
- ✅ 管理多个站点

**使用方法：**
1. 使用配置工具生成配置（网页或命令行）
2. 进入仓库 `Settings` → `Secrets and variables` → `Actions`
3. 新建 Secret：`NEWAPI_ACCOUNTS`
4. 粘贴配置并保存

---

#### 2. 浏览器本地存储（方便，需谨慎）

**安全性：** ⭐⭐⭐

**优点：**
- ✅ 使用方便，一键保存和加载
- ✅ 无需 GitHub 账号
- ✅ 数据存储在本地浏览器
- ✅ 下次访问自动提示恢复

**缺点：**
- ❌ **明文存储**，无加密保护
- ❌ 其他人使用你的电脑可能看到
- ❌ 换电脑或换浏览器需要重新配置
- ❌ 清除浏览器数据会丢失配置

**适用场景：**
- ✅ 临时测试配置
- ✅ 私人电脑
- ✅ 快速生成配置

**不适用场景：**
- ❌ 公共电脑
- ❌ 共享电脑
- ❌ 公司电脑

**使用方法：**
1. 打开 `config_generator.html`
2. 填写账号信息
3. 点击"💾 保存到本地"按钮
4. 下次访问点击"📂 从本地加载"

---

#### 3. 本地文件存储（适合开发）

**安全性：** ⭐⭐⭐⭐

**优点：**
- ✅ 文件级权限控制
- ✅ 可以加密文件
- ✅ 便于备份
- ✅ 适合本地开发测试

**缺点：**
- ❌ 需要手动管理文件
- ❌ 可能误提交到 Git

**适用场景：**
- ✅ 本地开发和测试
- ✅ 命令行工具使用
- ✅ 批量管理配置

**使用方法：**
```bash
# 使用命令行配置助手
python config_helper.py

# 会生成：
# - newapi_accounts.json
# - newapi_accounts.txt

# 这些文件已在 .gitignore 中，不会被提交
```

---

### 安全最佳实践

#### ✅ 推荐做法

1. **使用 GitHub Secrets 存储生产配置**
   - 所有自动签到都通过 GitHub Actions 执行
   - 配置安全加密存储

2. **本地存储仅用于临时测试**
   - 使用网页工具快速生成配置
   - 测试无误后复制到 GitHub Secrets
   - 测试完成后清除本地存储

3. **定期更新 Session Cookie**
   - 每月主动更新一次
   - Session 过期后及时更新

4. **仓库设为私有**
   - Fork 后将仓库改为 Private
   - 保护你的代码和配置

5. **不要分享配置**
   - Session Cookie 相当于登录凭证
   - 不要发送给任何人
   - 不要截图包含 Session 的页面

#### ❌ 避免做法

1. **不要提交敏感信息到代码仓库**
   - ❌ 不要在代码中硬编码 Session
   - ❌ 不要将配置文件提交到 Git
   - ❌ 不要在 Issue/PR 中暴露配置

2. **公共电脑不要使用本地存储**
   - ❌ 网吧、图书馆等公共场所
   - ❌ 公司电脑（可能被监控）
   - ❌ 共享电脑（其他人可能看到）

3. **不要使用不安全的分享方式**
   - ❌ 通过聊天软件明文发送
   - ❌ 存储在云笔记（如未加密）
   - ❌ 截图包含完整 Session

---

### Session Cookie 安全

#### Session Cookie 的风险

Session Cookie 相当于**临时密码**，拥有它的人可以：
- ✅ 以你的身份访问 API
- ✅ 查看你的账号信息
- ✅ 执行签到等操作
- ⚠️ 但**不能修改密码**或敏感设置（通常需要额外验证）

#### 保护 Session Cookie

1. **定期更新**
   - Session 会自动过期（7-30 天）
   - 建议每月主动更新一次
   - 重新登录会生成新的 Session

2. **使用 HTTPS**
   - 所有 NewAPI 站点都应使用 HTTPS
   - 避免中间人攻击

3. **不分享**
   - 不要发送给任何人
   - 不要截图包含 Session
   - 不要在公开场合展示

---

### GitHub Secrets 安全

#### GitHub Secrets 的安全性

- ✅ 加密存储在 GitHub 服务器
- ✅ 只有仓库所有者和协作者可管理
- ✅ Actions 运行日志中自动脱敏（显示为 `***`）
- ✅ 无法通过 GitHub API 读取原始值
- ✅ 支持审计日志

#### 最佳实践

1. **仓库设为私有**
   ```
   Settings → General → Danger Zone → Change visibility → Make private
   ```

2. **限制协作者**
   - 不要随意添加协作者
   - 协作者可以访问 Secrets

3. **定期审计**
   - 定期检查 Actions 运行日志
   - 确保 Session 未泄露

---

### 应急响应

#### 如果 Session 泄露了怎么办？

1. **立即重新登录**
   - 访问网站并重新登录
   - 这会使旧 Session 失效

2. **更新配置**
   - 获取新的 Session Cookie
   - 更新 GitHub Secrets
   - 清除本地存储（如果使用）

3. **检查账号安全**
   - 查看登录日志
   - 检查是否有异常操作
   - 必要时修改密码

4. **清理痕迹**
   - 删除包含 Session 的截图
   - 删除聊天记录中的 Session
   - 清除浏览器历史记录

---

### 安全级别总结

| 存储方式 | 安全性 | 便捷性 | 推荐场景 |
|---------|-------|-------|---------|
| GitHub Secrets | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 生产环境、长期使用 |
| 浏览器本地存储 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 私人电脑、临时测试 |
| 本地文件 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 开发测试 |
| 环境变量 | ⭐⭐⭐⭐ | ⭐⭐⭐ | 本地运行 |

**记住：安全性永远优先于便捷性！** 🔐

---

## 🛠️ 技术栈

- **语言：** Python 3.11+
- **HTTP 库：** requests
- **CI/CD：** GitHub Actions
- **配置工具：** HTML + JavaScript (网页版), Python (命令行版)
- **通知推送：** 钉钉机器人 / SMTP 邮件 / ServerChan

---

## 📦 项目文件说明

| 文件 | 说明 |
|------|------|
| `checkin.py` | 主签到脚本 |
| `lottery.py` | 中转站抽奖/翻卡模块（哈基米抽奖、维云翻卡） |
| `notifier.py` | 通知推送模块（邮件/Server酱） |
| `dingtalk_notifier.py` | 钉钉通知模块 |
| `test_checkin.py` | 单站点测试脚本 |
| `config_helper.py` | 命令行配置助手（交互式）|
| `config_generator.html` | 网页配置生成器（可视化）|
| `.env.example` | 通知推送环境变量配置模板 |
| `.github/workflows/checkin.yml` | GitHub Actions 工作流 |
| `requirements.txt` | Python 依赖 |
| `README.md` | 项目文档 |

---

## 📄 许可证

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 🙏 致谢

- [QuantumNous/new-api](https://github.com/QuantumNous/new-api) —— 本项目所对接的上游网关系统
- 所有通过 Issue、PR 和 Fork 参与改进的贡献者
- 感谢 [newapi-ai-check-in](https://github.com/aceHubert/newapi-ai-check-in) 等同类项目提供的思路参考

---

## ⚠️ 免责声明

1. 本项目仅供学习交流和个人自动化使用，请遵守目标站点的服务条款
2. 请合理使用签到功能，不要对站点造成过大访问压力（脚本已内置限流处理）
3. 使用本项目产生的任何账号风险（封号、降权等）由使用者自行承担
4. 请勿将本项目用于任何商业用途或恶意场景
5. 本项目不存储、不上传任何用户的凭证信息至开发者服务器——所有配置均保存在用户自己的环境（本地 `.env`、GitHub Secrets 或用户自己的 WebDAV）中

---

## ⭐ 支持项目

如果这个项目对你有帮助，欢迎点一个 **Star** ⭐ 支持一下！

你也可以通过以下方式支持：

- 🐛 提交 [Issue](https://github.com/Jasonliu-0/Newapi-checkin/issues) 反馈问题或建议新功能
- 🔀 提交 Pull Request 改进代码
- 📢 推荐给有需要的朋友

---

## 📮 反馈

如有问题或建议，请提交 [Issue](https://github.com/Jasonliu-0/Newapi-checkin/issues)。
