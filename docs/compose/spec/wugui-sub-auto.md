---
feature: wugui-sub-auto
status: in-progress
updated: 2026-09-22
branch: master
commits: # filled at delivery
---

# 乌龟订阅自动解锁 + daed 更新

> Project override（相对 compose-next 默认）：本仓库既有 compose 规格均直接在本工作区 `master` 交付（见 `docs/compose/spec/{firmware-daed-bake,daed-board-ux-perf,router-optimize-20260914}.md` 的 `branch: master` / `commits: n/a`），且会话隔离禁止 `git worktree add`。故沿用项目惯例在本工作区实现，不另建 worktree。

## Report

## [S1] Problem

乌龟机场（wgjsq08.vip，Xboard 面板）开了「订阅更新开关」（subscribe lock）：默认锁定时订阅 URL `https://119.29.57.170:38888/wuguisub?token=…` 返回 **403**。用户每天必须：

1. 打开 `https://wgjsq08.vip/#/dashboard` 登录并点开「订阅更新开关」；
2. 再到 daed 手动触发「乌龟」订阅更新。

开关解锁后仅限时可拉订阅（前端文案「…分钟后自动关闭」），到点自动上锁。daed 侧 cron（`10 */6 * * *`）在锁住时拉取必然 403，无法自愈。

目标：**一劳永逸**——路由器每天自动「解锁 → 触发 daed 更新」，用户不再碰网页；不主动上锁，等机场倒计时自动关。

## [S2] Design

### 已探明的 API 契约（2026-09-22 路由器侧实测）

站点前端为 Vue SPA，`window._config.baseURL = '/wuguiapi'`，后端为 Xboard 风格（404 文案 `The route api/v1/...` 印证前缀）。**PC 本机 TLS 握手对 wgjsq08.vip 不稳，路由器侧 200 正常**——这是选路由器 cron 的硬理由。

| 步骤 | 方法与路径 | 请求 | 实测响应 |
|---|---|---|---|
| 登录 | `POST /wuguiapi/passport/auth/login` | `{"email","password"}` | 200 `{"status":"success","data":{"token":"<sub-token>","auth_data":"Bearer <jwt-like>","is_admin":false}}` |
| 解锁 | `POST /wuguiapi/user/subscribe/unlock` | **`Authorization: <auth_data>`**（已含 `Bearer `），body `{}` | 200 `{"data":{"locked":false,"expires_at":…,"duration_minutes":10,"daily_limit":5,"daily_used":N,"daily_remaining":M}}` |
| 上锁（本方案不用） | `POST /wuguiapi/user/subscribe/lock` | 同上 | — |
| 订阅信息 | `GET /wuguiapi/user/getSubscribe` | 同上 | 200 含 **`data.subscribe_url`**、`data.token`（与 URL 中 token 一致） |
| 拉节点 | `GET <subscribe_url>` | 无鉴权 | 解锁窗口内 200 + base64 节点列表；锁住或 **token 失效** 均 403 |

**鉴权陷阱（实测）**：`Authorization: Bearer <data.token>` → 403「未登录」。必须用 `data.auth_data` 原样作头（或去掉 `Bearer ` 前缀后再加）。`data.token` 是**订阅 URL 里的 token**，不是 API 凭证。

**订阅 token 会变（本次根因）**：daed 里旧链接 `…?token=f9338c7e…` 在解锁后仍 403 `Invalid request`；`getSubscribe.subscribe_url` 已是 `…?token=68d4b499…`，解锁后 200/9480B。故脚本**必须先同步 daed 订阅链接**再 `updateSubscription`。

**解锁窗口**：`duration_minutes=10`、`daily_limit=5`。每日 1 次 cron 远低于限额；解锁后 10 分钟内完成 daed 更新即可，不主动上锁。

前端另有 `toggleSubscribeLock` / `lock-state-locked` / `formattedRemaining` / `expires_at` 等，与上述字段一致。

daed 侧（GraphQL `http://192.168.31.1:2023/graphql`）：

- 取 token：`{ token(username:"root", password:"…") }`
- 更新订阅：`mutation { updateSubscription(id: "<乌龟id>") { id tag } }`（**勿查顶层 `error`**；订阅 id 现为 `Y3Vyc29yMw`，tag `乌龟`）
- 订阅更新是「删旧建新」式对账；组走 `groupAddSubscriptions` + `nameFilterRegex` 匹配即可自动补员。**不需要** `run(dry:false)`（与 `update_cfhk.py` 一致）。

### 行为

路由器 `/usr/bin/wugui-sub-update.sh`（POSIX sh + curl + jsonfilter）每日 cron：

1. 读 `/etc/wugui-sub.conf`（chmod 600）；
2. 登录乌龟 → 取 `auth_data`（API 鉴权）与 `subscribe_url`（当前订阅直链）；
3. 对照 daed 订阅 `link`，若 token/URL 已变则 `updateSubscriptionLink` **同步链接**（防 token 轮换后永久 403）；
4. `POST /user/subscribe/unlock`（用 `auth_data` 作 Authorization；**不**调用 lock，等 10 分钟自动关）；
5. 立刻 GraphQL `updateSubscription(乌龟)`；
6. 结果追加日志 `/tmp/wugui-sub-update.log`（保留最近 50 行），退出码 0=成功 / 非 0=失败。

配套：

- **关闭 daed 内置 cron 对乌龟的自动更新**（`updateSubscriptionCron cronEnable:false`），避免锁住时 403 刷失败；由本脚本独占更新时机。
- cron：`/etc/crontabs/root` 增加 `50 5 * * * /usr/bin/wugui-sub-update.sh`（每日 05:50，用户起床前完成）。
- PC 侧 `wugui/deploy_wugui_sub.py`：SSH 部署脚本/配置模板/cron，并执行一次「关闭 daed 乌龟 cron」。凭据写在路由器 `/etc/wugui-sub.conf`，**不进 git**。

### 配置文件契约（`/etc/wugui-sub.conf`）

```
WUGUI_EMAIL='...'
WUGUI_PASSWORD='...'
WUGUI_API='https://wgjsq08.vip/wuguiapi'
DAED_URL='http://192.168.31.1:2023/graphql'
DAED_USER='root'
DAED_PASS='...'
DAED_SUB_ID='Y3Vyc29yMw'
DAED_SUB_TAG='乌龟'
```

（值一律 shell 单引号包裹；部署器用 `sh_quote` 写入，可含空格/`$`/`#`。）

### 错误行为

- 任一步失败：日志写明步骤与响应片段，exit 1；不吞错（含 unlock 非 200）。
- API 鉴权只认 `data.auth_data`；`data.token` 仅用于拼 `subscribe_url` 对照。
- JSON 请求体对插入值做 `\`/`"`/TAB/CR 转义；部署器侧 mutation 用 Python `json.dumps` 生成，避免 shell 格式串注入。
- 解锁后 `sleep 1` 再更新 daed（给后端一点落锁状态时间）。
- 锁目录写入 PID；PID 已死则回收陈旧锁，避免 SIGKILL 后永久卡死。
- updateSubscription 拉取失败（GraphQL errors）视为失败并记日志；**不**重试自动上锁。
- 脚本幂等：可手动重跑；cron 重叠由文件锁（`/tmp/wugui-sub-update.lock`）防止。

### 测试边界

- 本地：`sh -n` 语法；配置模板字段齐全；部署脚本可 dry-run 列出将执行的 SSH 命令。
- 联调（凭据已具备时）：手动跑一次脚本，验收 ①解锁成功 ②daed 订阅 `updatedAt` 刷新且 `nodes.totalCount>0` ③日志三步皆 OK。
- 不测：机场自动上锁时刻、daed 组成员名映射（既有 steer 自愈已覆盖）、YToo 等其它订阅。

## [S3] Out of Scope

- 更新后主动上锁（用户明确选择等自动关）
- 把订阅内容缓存到 GitHub/CF 再分发（可作后续加固，本期不做）
- PC 计划任务 / 双端
- 改机场解锁时长（服务端配置，用户不可控）
- YToo 等其它需开开关的订阅
- daed-board UI 改动

## Tasks

- [ ] T1: 写 `wugui/wugui-sub-update.sh`（登录→同步订阅链接→解锁→daed updateSubscription→日志） — acceptance: `bash -n` 通过，步骤与契约一致，含文件锁与配置读取 (covers: S2)
- [ ] T2: 写 `wugui/wugui-sub.conf.example` 与 `wugui/deploy_wugui_sub.py`（部署脚本/配置/cron/关 daed 乌龟 cron） — acceptance: example 字段齐全不含真实密码；deploy 支持 `--dry` 打印将执行命令 (covers: S2)
- [ ] T3: 部署到路由器并关闭 daed 乌龟 cron、写入真实配置与 cron — acceptance: 路由器存在 `/usr/bin/wugui-sub-update.sh` 可执行、`/etc/wugui-sub.conf` mode 600、crontab 含 05:50 行、daed 乌龟 cronEnable=false (covers: S2; depends: T1, T2)
- [ ] T4: 联调跑通一次全链路 — acceptance: 脚本 exit 0，日志显示 login/sync-link/unlock/daed 四步成功，daed 订阅 link 已是当前 token 且 updatedAt 刷新 (covers: S2; depends: T3)
