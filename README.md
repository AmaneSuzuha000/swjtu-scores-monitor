在你自己fork的仓库里面点击 Sync Fork -> Update Branch 即可更新到最新版本
  <img width="917" height="395" alt="image" src="https://github.com/user-attachments/assets/22733e69-f1f1-4491-b970-064b46c8ac9d" />


# 西南交大成绩监控系统

自动监控西南交通大学教务系统的成绩变化，当检测到新成绩或成绩更新时，通过邮件发送通知。使用 QQ 邮箱可以做到直接收到微信通知。

**功能特点：**
- 🆓 完全免费，利用 GitHub Action
- ☁️ **无需克隆代码配置环境，也无需自己的服务器**
- ⏰ 自动定时运行（北京时间 6:00-23:59，每20分钟检查一次）
- 🔒 隐私安全，敏感信息加密存储
- 📧 成绩变化时自动邮件通知

## 一、隐私与安全说明

### 为什么本项目是安全的？

1. **所有敏感信息都存储在 GitHub Secrets 中**
   - 学号、密码、邮箱授权码等信息不会出现在代码中
   - GitHub Secrets 使用加密存储，外部无法访问
   - 运行日志中 Secrets 会被自动隐藏（显示为 `***`）
   - 运行日志在公开仓库下所有人可见，但无任何敏感信息

2. **仓库可公开**
   - Fork 后的仓库可以是公开的，不影响安全性
   - 代码中不包含任何密码或敏感信息
   - 只有你能在自己的仓库中配置 Secrets

3. **数据存储方式**
   - 成绩数据存储在你自己的 GitHub Gist 中（私有）
   - 只有你的 Personal Access Token 能访问
   - **Gist 可见性说明**：
     - 程序创建的 Gist 默认为 **Secret（私密）** 类型
     - Secret Gist 不会出现在你的公开 Gist 列表中
     - 只有知道 Gist URL 或拥有 Token 的人才能访问
     - 即使仓库是公开的，Gist 数据也是私密的

### ⚠️ 安全使用原则

- 永远不要把密码直接写在代码文件中
- 永远使用 GitHub Secrets 来存储敏感信息
- 不要将 Secrets 的值分享给他人
- **邮箱授权码和 Token 仅显示一次，请妥善保存**


## 二、前置准备

### 2.1 你需要准备

1. **你的 GitHub 账号**
2. **西南交大新教务（yhxt）的登录凭据**——推荐用 `YHXT_YTOKEN`（浏览器登录后从 localStorage 复制），也可以直接给统一认证账号密码
3. **一个邮箱**（推荐使用QQ邮箱，可以绑定微信收取实时通知）

### 3.2 获取每个 Secret（密钥配置）

#### ① YHXT_YTOKEN（推荐）或 SWJTU_USERNAME / SWJTU_PASSWORD

本项目已经从**旧教务（jwc，含验证码）**迁移到**新教务（yhxt）**，认证方式是请求头里的 `ytoken`：

- `YHXT_YTOKEN`（**推荐**）：一个长效登录令牌。获取方法：
  1. 浏览器打开 https://yhxt.swjtu.edu.cn/study/ 并完成登录
  2. F12 → Application（应用）→ Local Storage → 站点域名 → 复制 `ytoken` 的值
  3. 把它配成名为 `YHXT_YTOKEN` 的 Secret
  - 优点：**不需要账号密码**，不涉及验证码，Actions 里也不会因为风控失败
  - 失效后重新复制一次即可（日志会明确提示“ytoken 已失效”，不会误判成“没有成绩”）

- `SWJTU_USERNAME` / `SWJTU_PASSWORD`（**可选兜底**）：统一认证账号密码。
  未配置 `YHXT_YTOKEN` 时，程序会走无头 CAS 登录自动换 token。
  CAS 有风控（可能出现图形验证码），因此仅建议作为后备方案。

- `YHXT_AUTH_STATE`（可选）：指向浏览器导出的 auth-state JSON 文件路径，程序会从里面读 `ytoken`。

#### ② SMTP_HOST、NOTIFY_EMAIL 和 EMAIL_PASSWORD

这三个配置用于发送邮件通知，推荐使用 QQ 邮箱

本项目采用「**自己给自己发邮件**」的设计：

- `NOTIFY_EMAIL` 既是发件人，也是收件人
- 你只需要配置一个邮箱地址
- 程序用你的邮箱给你自己发送通知

**设计原因**
1. **配置简单**：只需一个邮箱，无需额外准备发件邮箱
2. **安全可靠**：邮件在你自己的邮箱之间传递

**推荐使用 QQ 邮箱的原因：**
- QQ 邮箱可以绑定微信，收到邮件时微信会立即推送通知
- 相当于免费获得了微信消息提醒功能
- 设置方法：微信搜索「QQ邮箱提醒」进入 QQ 邮箱提醒功能，绑定该 QQ 邮箱，设置选择接受邮件提醒即可

以下是QQ邮箱的配置方法：

1. **SMTP_HOST**：`smtp.qq.com`
2. **NOTIFY_EMAIL**：你的 QQ 邮箱地址（如 `12345678@qq.com`）
3. **EMAIL_PASSWORD**：需要获取**授权码**（不是QQ密码）

**如何获取 QQ 邮箱授权码：**

1. 登录 QQ 邮箱网页版：https://mail.qq.com
2. 进入「账号与安全」
3. 进入「安全设置」
4. 找到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务」并开启
5. 点击「生成授权码」
6. 获得一个 16 位授权码（如：`abcdabcdabcdabcd`）
7. 这个授权码就是 EMAIL_PASSWORD 的值，**该字符串仅在授权码页面展示一次，请合理保存**
8. 途中可能经过三次手机号验证，这是正常的

#### ③ GIST_PAT（GitHub Personal Access Token）

GitHub Personal Access Token（个人访问令牌）是用来授权程序访问你的 GitHub Gist 的凭证。本项目使用 Gist 来存储你的成绩数据。

**如何创建 GIST_PAT：**

1. **登录 GitHub**，点击右上角头像

2. **进入 Settings**
   - 点击下拉菜单中的「Settings」

3. **找到 Developer settings**
   - 在左侧菜单最底部点击「Developer settings」

4. **创建 Personal access tokens**
   - 点击左侧「Personal access tokens」→「Tokens (classic)」
   - 点击右上角「Generate new token」→「Generate new token (classic)」

5. **配置 Token**
   - **Note**（备注）：填写一个描述，如 `swjtu-scores-monitor`
   - **Expiration**（有效期）：建议选择「No expiration」（永不过期）或「1 year」
   - **Select scopes**（权限选择）：**只勾选 `gist`**
     ```
     ☑️ gist
         Create gists
     ```
   - 其他权限不勾选

6. **生成并保存**
   - 点击底部「Generate token」
   - 复制生成的 Token（格式如：`ghp_xxxxxxxxxxxxxxxxxxxx`）
   - **重要：这个 Token 也只会显示一次，请立即复制保存**
   - 这个 Token 就是 `GIST_PAT` 的值


## 三、部署步骤

### 步骤 1：Fork 本项目

1. 在项目主页点击右上角「Fork」按钮
2. Fork 到你自己的账号下

### 步骤 2：配置 GitHub Secrets

1. 进入你 Fork 的仓库，点击「Settings」
2. 左侧菜单找到「Secrets and variables」→「Actions」
3. 点击「New repository secret」，添加以下 Secrets：

| Name | Secret | 必填 | 说明 |
|------|---|---|------|
| `YHXT_YTOKEN` | 一串令牌 | ✅ | 新教务登录令牌（见 3.2 ①），**推荐** |
| `SMTP_HOST` | smtp.qq.com | ✅ | 邮箱 SMTP 服务器地址 |
| `NOTIFY_EMAIL` | your@qq.com | ✅ | 接收通知的邮箱 |
| `EMAIL_PASSWORD` | 授权码 | ✅ | 邮箱授权码（不是邮箱密码） |
| `GIST_PAT` | ghp_xxx... | ✅ | GitHub Personal Access Token |
| `SWJTU_USERNAME` | 你的学号 | ⬜ | 统一认证学号（仅在没有 ytoken 时用于自动登录） |
| `SWJTU_PASSWORD` | 你的密码 | ⬜ | 统一认证密码（同上） |

**添加方式：**
- 在「Name」输入框填入 Secret 名称（如 `YHXT_YTOKEN`）
- 在「Secret」输入框填入对应的值
- 点击「Add secret」
- 重复以上步骤添加所有 Secrets

### 步骤 3：启用 GitHub Actions

1. **进入 Actions 页面**
   - 点击仓库顶部的「Actions」标签

2. **启用 Workflows**
   - 如果看到提示「Workflows aren't being run on this forked repository」
   - 点击「I understand my workflows, go ahead and enable them」

3. **确认 Monitor Scores 工作流已启用**
   - 在左侧列表中找到「Monitor Scores」
   - 确保它处于启用状态
   - （别的workflow我用作测试，不用管）

### 步骤 4：手动测试运行

1. **在 Actions 页面**，点击左侧的「Monitor Scores」

2. **手动触发运行**
   - 点击右上角「Run workflow」下拉按钮
   - 点击「Run workflow」确认

3. **查看运行结果**
   - 刷新页面会看到正在运行的 workflow
   - 点击正在运行的任务，再点击run-job，查看实时日志
   - 展开Run Script日志，如果配置正确，应该能看到：
     ```
     --- 任务开始: 监控成绩变化 ---
     正在从数据库获取历史成绩...
     正在登录教务系统获取最新成绩...
     已登录新教务：某某某 (2025xxxxxx) 工程2025-01班
     成功获取到 37 条成绩记录。
     正在比较成绩变化...
     未检测到成绩变化。
     --- 任务完成 ---
     ```
   - 该运行结果无敏感信息

4. **检查邮箱**
   - 如果是首次运行，你会收到带有你所有成绩的邮件；如果有成绩变化，你也会收到邮件通知

## 四、常见问题

### Q1：登录失败怎么办？

**可能原因：**
1. `ytoken` 已失效（最常见）
   - 日志里会出现 `ytoken 已失效（HTTP 401）` 或 `会话已失效`
   - 按 3.2 ① 重新从浏览器复制一次 `ytoken` 并更新 Secret 即可
   - 程序**不会**把“登录失效”误判成“没有成绩”，所以不会误报或漏报
   
2. 教务系统维护或关闭外网访问
   - 尝试在浏览器手动登录 https://yhxt.swjtu.edu.cn/study/ 确认
   
3. 走的是 CAS 账号密码兜底方案，被风控拦了
   - CAS 可能在密码错误多次后要求图形验证码
   - 日志会提示“需要验证码/被风控拦截”
   - 解决办法：改用 `YHXT_YTOKEN`（推荐），或人工在浏览器登录一次解除风控

### Q2：收不到邮件通知？

**检查清单：**

1. **Secrets 配置是否正确**
   - 确认 `SMTP_HOST`、`NOTIFY_EMAIL`、`EMAIL_PASSWORD` 都已配置
   - 确认 `EMAIL_PASSWORD` 使用的是授权码，不是登录密码

2. **检查垃圾邮件箱**
   - 第一次接收时可能被识别为垃圾邮件

3. **查看运行日志**
   - 进入 Actions 查看详细日志
   - 搜索「邮件」或「SMTP」相关错误信息

4. **SMTP 服务是否开启**
   - 确认邮箱已开启 SMTP 服务
   - QQ 邮箱：设置 → 账户 → POP3/SMTP 服务

5. **端口问题**
   - 项目默认使用 465 端口
   - 如需修改，可在 Secrets 中添加 `SMTP_PORT`

### Q3：如何查看当前存储的成绩数据？

1. 访问你的 GitHub Gists：https://gist.github.com/你的github用户名
2. 找到描述为 `just_for_swjtu_scores_monitor` 的 Gist
3. 文件名为 `scores.json`
4. 点击查看即可看到存储的成绩 JSON 数据

### Q4：GitHub Actions 免费额度够用吗？

**免费账户限制：**
- 每月 2000 分钟运行时间
- 公开仓库不消耗额度
- 私有仓库消耗额度

**本项目消耗：**
- 单次运行约 30s
- 每天运行约 54 次（20分钟间隔，18小时）
- 每月约 54 × 30 × 0.5 = 810 分钟

**建议：**
- 保持仓库为公开（Public）→ 不消耗额度

### Q5：为什么有时候运行失败？

**正常情况：**
- 新教务接口临时抖动/超时：下次运行会自动恢复
- `ytoken` 过期：更新一次 Secret 即可（不会误报成绩）
- GitHub Actions 服务波动：偶尔发生

**不影响使用：**
- 只要不是连续多次失败，都属于正常现象
- 20 分钟后会自动重新运行

### Q6：如何更新项目代码？

如果原项目有更新，同步到你的 Fork：

1. 在你的仓库页面，点击「Sync fork」
2. 点击「Update branch」
3. Secrets 配置会保留，无需重新配置

### Q7：可以监控多个账号吗？

当前版本只支持单账号。如需监控多个账号：

1. 再次 Fork 项目（使用不同的仓库名）
2. 为每个仓库配置不同的 Secrets
3. 每个仓库独立运行

---
# 接下来是与项目部署使用无关的内容，可以选择性阅读

## 五、monitor.yml 工作原理

### 运行时间

```yaml
schedule:
  - cron: '*/20 0-15,22-23 * * *'
```

- **北京时间**：6:00 - 23:59，每 20 分钟运行一次
- **UTC时间**：22:00 - 15:59（GitHub Actions 使用 UTC 时间）
- 北京时间 00:00 - 5:59 教务处暂停外部访问，故不运行
- 由于 GitHub Actions 调度原因，时间可能偏移最多 15 分钟

### 工作流程

1. **检出代码**：获取最新的项目代码
2. **安装依赖**：使用 uv 安装 Python 依赖
3. **运行监控脚本**：
   - 从 GitHub Gist 读取上次保存的成绩
   - 登录教务系统获取最新成绩
   - 对比新旧成绩，检测变化
   - 如果有变化，发送邮件通知
   - 将最新成绩保存到 Gist

### 检测的变化类型

- 新增课程成绩
- 成绩分数变化
- 新增平时成绩
- 平时成绩变化


## 六、使用与维护

### 查看运行日志

1. 进入仓库的「Actions」页面
2. 点击任意一次运行记录
3. 点击「run-job」查看详细日志
4. 可以看到登录过程、成绩获取、变化检测等详细信息

### 手动触发监控

1. 进入「Actions」→「Monitor Scores」
2. 点击「Run workflow」
3. 点击「Run workflow」确认
4. 适合测试或立即检查成绩

### 修改监控频率

编辑 `.github/workflows/monitor.yml`，修改 cron 表达式：

```yaml
# 每10分钟
- cron: '*/10 0-15,22-23 * * *'

# 每小时
- cron: '0 0-15,22-23 * * *'
```

**注意**：过于频繁可能被教务系统限制访问

### 暂停监控

1. 进入「Actions」→「Monitor Scores」
2. 点击右上角「...」菜单
3. 选择「Disable workflow」

### 恢复监控

重新启用 workflow 即可


## 七、技术说明

### 使用的技术栈

- **Python 3.12**：主要编程语言
- **uv**：快速的 Python 包管理器
- **requests**：调用新教务（yhxt）的 JSON API
- **纯 Python AES-CBC**：复刻 CAS 登录页的密码加密（无第三方加密依赖，见 `utils/aes_cbc.py`）
- **GitHub Gist**：数据存储
- **SMTP**：邮件发送

### 项目结构

```
.github/workflows/
  └── monitor.yml          # GitHub Actions 工作流配置
actions/
  └── index.py             # 主要业务逻辑
api/
  └── index.py             # Vercel Serverless 入口（可选）
utils/
  ├── yhxt.py              # 新教务客户端：登录 + 成绩接口 + 归一化
  ├── aes_cbc.py           # 纯 Python AES-CBC（CAS 密码加密）
  ├── fetcher.py           # 兼容门面（ScoreFetcher），委托给 yhxt.py
  ├── database.py          # Gist 数据存储
  ├── notify.py            # 邮件通知
  └── ocr.py               # 旧教务验证码识别（已随迁移弃用，保留备查）
test/
  ├── test_yhxt.py         # 新教务客户端离线测试
  ├── test_aes_cbc.py      # AES 向量测试
  └── score.py             # 手动抓取/排查脚本
```

## 八、Gist 数据存储说明

### 什么是 Gist？

GitHub Gist 是 GitHub 提供的代码片段托管服务，本项目使用它来存储你的成绩数据。每次运行时，程序会从 Gist 读取上次的成绩，对比后将最新成绩写回 Gist。

### Gist 的创建与管理

- **自动创建**：首次运行时，程序会自动创建一个名为 `swjtu_scores_data` 的 **私有 Gist**
- **文件名**：`scores.json`
- **Gist 描述**：`just_for_swjtu_scores_monitor`
- **访问权限**：只有你自己（通过 GIST_PAT）可以访问

### 如何查看 Gist 数据？

1. 访问 https://gist.github.com/你的用户名
2. 找到描述为 `just_for_swjtu_scores_monitor` 的 Gist
3. 点击查看 `scores.json` 文件内容

### 如何删除 Gist 数据（重置）？

如果你想重置成绩监控（比如清空历史数据重新开始）：

1. 访问 https://gist.github.com/你的用户名
2. 找到并点击描述为 `just_for_swjtu_scores_monitor` 的 Gist
3. 点击右上角「Delete」按钮删除
4. 下次运行时，程序会自动创建新的 Gist

### Gist 数据格式

存储的 JSON 数据格式如下：

```json
{
  "课程名称1": {
    "score": "85",
    "daily_scores": ["90", "88", "92"]
  },
  "课程名称2": {
    "score": "90",
    "daily_scores": []
  }
}
```

- `score`：期末/总评成绩
- `daily_scores`：平时成绩列表


## 九、新教务（yhxt）接口与认证说明

> 本节替代了原先的「OCR 验证码识别说明」。旧教务（jwc）已停用；新教务不发验证码，
> 因此不需要 OCR，`utils/ocr.py` 与 `utils/templates/` 仅作历史保留。

### 认证：ytoken

新教务（`https://yhxt.swjtu.edu.cn`）的前端把登录令牌存在 localStorage 的 `ytoken`，
之后所有 `/yethan/*` 请求都带请求头 `ytoken: <token>`。所以本项目只需要一个令牌。

两条取令牌的路：

1. **直接给令牌**（推荐）：`YHXT_YTOKEN`，或 `YHXT_AUTH_STATE` 指向导出的 JSON。
2. **无头 CAS 登录**（兜底）：给 `SWJTU_USERNAME`/`SWJTU_PASSWORD`，程序会
   - 打开 `https://cas.swjtu.edu.cn/authserver/login?service=https://yhxt.swjtu.edu.cn/cas-login.html`
   - 用页面里的 `execution` 与 `pwdEncryptSalt` 构造表单，密码按前端算法加密提交
     （`AES-CBC/PKCS7`，key=salt，明文 = 64 个随机字符 + 密码，见 `utils/aes_cbc.py`）
   - 跟随跳转取出 `ticket`，再请求 `/yethan/public/casCallback?ticket=...` 换回 `ytoken`

### 用到的成绩接口

| 用途 | 接口 | 关键字段 |
|---|---|---|
| 全部已出成绩（含任课教师） | `GET /yethan/score/exam-mark-all/list` | `courseName` `staffName` `mark` `markStr` `creditHour` `termName` `gradeType` `examType` |
| 学生成绩总表（含本学期在修课程） | `GET /yethan/public/score/getAllScoreByStudentId` | `scoreAllList[]` 同样字段，未出分时 `mark=null` |
| 会话自检 | `GET /yethan/register/student-course/info` | `studentId` `studentName` `className` |

程序把两张表按 `(学期, 课程代码)` 合并后归一化成统一结构：
- 已出成绩以「成绩明细表」为准（能拿到教师名，用于生成稳定的对比 key）
- 在修但未出分的课程来自「成绩总表」，`成绩` 为空；等出分后自然被识别为「新增总成绩」

### 与旧实现相比修掉的问题

1. **不再把“登录失效”误判成“没有成绩”**：`ytoken` 失效返回 HTTP 401，
   程序会显式报“会话已失效”并放弃本轮对比，而不是写入一份空成绩单。
   （旧 jwc 是 302 回登录页，靠“没找到表格”判断，会误报。）
2. **不再依赖验证码 OCR**：少一条最不稳定的链路，也少了 PIL 等重依赖。
3. **编码问题消失**：新教务返回 JSON（UTF-8），不再有 `Content-Type` 缺 charset
   导致中文课程名乱码、进而让每门课都被判为“新增”的问题。

## 十、邮件成绩通知说明

### 通知触发条件

以下情况会触发邮件通知：

- **新增课程成绩**：检测到之前没有的课程出现成绩
- **成绩分数变化**：已有课程的成绩发生变更
- **新增平时成绩**：检测到新的平时成绩记录
- **平时成绩变化**：已有平时成绩发生变更
- **首次运行**：第一次运行时会发送当前所有成绩

### 邮件格式

通知邮件采用 HTML 格式，包含：

- **成绩变化表格**：清晰展示课程名称和对应成绩
- **成绩高亮**：新成绩用醒目颜色标注
- **变化说明**：标注是新增还是更新

### 邮件发送配置

| 配置项 | 说明 |
|--------|------|
| `SMTP_HOST` | 邮件服务器地址（如 `smtp.qq.com`） |
| `NOTIFY_EMAIL` | 发送和接收邮件的邮箱地址 |
| `EMAIL_PASSWORD` | 邮箱授权码（非登录密码） |
| `SMTP_PORT` | 可选，默认 465（SSL 加密） |

### 支持的邮箱

理论上支持所有开启 SMTP 服务的邮箱。

### 收不到邮件？

1. **检查垃圾邮件箱**：首次接收可能被标记为垃圾邮件
2. **确认授权码正确**：使用邮箱授权码，而非登录密码
3. **确认 SMTP 已开启**：在邮箱设置中开启 SMTP 服务
4. **查看运行日志**：Actions 日志会显示邮件发送状态

### 自定义端口

如需使用非默认端口（如 587），可添加 Secret：
- **Name**: `SMTP_PORT`
- **Secret**: `587`

### 可选环境变量

以下变量都有默认值，**不配置也能正常运行**；仅在需要调整超时或教务地址时使用。
配置方式与上面相同（Settings → Secrets and variables → Actions → New repository secret）。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `YHXT_YTOKEN` | 无 | 新教务登录令牌（**强烈推荐**，见 3.2 ①）。与下面两个账号密码互斥，优先使用。 |
| `YHXT_AUTH_STATE` | 无 | 浏览器导出的认证态 JSON 路径，从中读取 `ytoken`。 |
| `SMTP_TIMEOUT` | `30` | 邮件服务器连接/发送超时（秒）。不设超时时，SMTP 卡住会一直挂到 Actions 6 小时上限。 |
| `GIST_API_TIMEOUT` | `20` | GitHub Gist API 请求超时（秒）。历史成绩读写失败会中止本轮对比，而不是误判为「没有历史」。 |
| `YHXT_API_TIMEOUT` | `20` | 新教务 API 请求超时（秒）。 |
| `YHXT_BASE` | `https://yhxt.swjtu.edu.cn/yethan` | 新教务 API 基址，域名调整时可覆盖。 |
| `CAS_BASE` | `https://cas.swjtu.edu.cn/authserver` | 统一认证基址，走账号密码兜底登录时使用。 |
| `YHXT_SERVICE_URL` | `https://yhxt.swjtu.edu.cn/cas-login.html` | CAS 登录的 `service` 参数，一般无需修改。 |

> 说明：读取或保存历史成绩失败时，任务会**明确报错退出**而不是静默按「无历史」处理——
> 后者会把整份成绩单当成新增并群发通知。会话失效（HTTP 401）同样会中止本轮，
> 不会写入一份空成绩单。

## 十一、致谢与支持

如果这个项目对你有帮助，欢迎：

- ⭐ Star 本项目
- 🐛 提交 Issue 反馈问题
- 🔀 提交 Pull Request 改进项目








