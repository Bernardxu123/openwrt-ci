# DSH Pocket 外网直连（IPv6 + DDNS）修复与提速 — 2026-11-01

## 1. 背景

用户反馈：手机外网走 `https://dsh.290490.xyz:3081`（IPv6 直连）比 DSH 内置的 Cloudflare 隧道快，但近期"直连"打不开/很慢；同时要求确认 **DDNS 在 IP 变化时是否会跟随**，并强调 **路由器很轻量，不要频繁检测**（IPv6 只在重启/重拨时变）。

## 2. 现场证据（2026-11-01 01:30–08:10）

| 项 | 实测 |
|---|---|
| Pocket 监听 | PC `0.0.0.0:3082`（DSH 16:11 重启后从 3081 漂移），3081 拒绝连接 |
| nginx | `[::]:3081` 在听；上游写死 `192.168.31.218:3081` + `.222 backup`；error.log：`upstream timed out`、`.222 Host is unreachable`；一次请求 **8.1s 后 502** |
| 防火墙 | 两条未记录 DNAT：wan 3081/3082 → PC 的 IPv6 `2408:820c:820f:9950:d4d4:…`；`Allow-DSH-Pocket-IPv6` 计数 0 |
| 外网 VPS(161.118.196.196) | ping 路由器 IPv6 通（77–89ms）；tcp 3081/3082 **超时**；2222（SSH DNAT）通 |
| DNAT 失败原因 | Pocket 只监听 `0.0.0.0`（IPv4），IPv6 DNAT 无法到达；且 DNAT 绕过 nginx 的 TLS/Host 改写 |
| nginx 能力 | 1.26.3，`--with-http_v2_module`；实际 ALPN = **http/1.1** |
| 缓存/gzip | `/assets/*` 无 Cache-Control；HTML 42670 B 未压缩；`plugins/??…` 4.2MB gz 已有 immutable |
| DDNS | CF AAAA = `2408:820c:8200:44ef:b0ad:28b5:22a5:bb66` = pppoe-wan；`modified_on 2026-10-31T09:46:10Z`；`/etc/dsh-ddns-last` mtime 17:45；comment `dsh-pocket-router-ddns` |
| 隧道 | cloudflared 已停（服务 Disabled），`dsh.trustreachclf.com` → CF 530 |

## 3. 根因

1. **端口漂移**：DSH Pocket 默认 3081，启动时被占会 `+1..+9`。当天 DSH 重启后落到 3082，nginx 仍指 3081 ⇒ 502。
2. **DNAT 抢流量**：两条 redirect 在 prerouting 就把 wan 3081/3082 劫到 PC 的 IPv6；Pocket 只监听 IPv4 ⇒ 永远超时（外网 VPS 实测）。
3. **故障放大**：`.222` 是已下线的 WiFi 备份，`proxy_connect_timeout 5s` + 重试让失败要等 8 秒。
4. **性能余量**：无 HTTP/2、无静态缓存、HTML 未压缩、上游无 keepalive。

## 4. 改动清单

### 4.1 PC / DSH Pocket
- `%USERPROFILE%\.dsh\dsh-pocket\settings.json` 增加 `"proxyPort": 3081`（插件启动时读取；本次未重启 DSH，当前仍 3082，由路由器 watchdog 兼容；下次重启回到 3081）。

### 4.2 路由器 nginx（`/etc/dsh-nginx/nginx.conf`）
- `http2 on`（客户端侧 HTTP/2；TLS1.3）。
- 上游改为 `include /etc/dsh-nginx/upstream.conf` + `keepalive 16`；`map` 让非 WS 请求发空 `Connection`。
- `/assets/` 加 `Cache-Control: public, max-age=31536000, immutable`（文件名带 hash）。
- 开启 gzip（HTML/JSON/SVG/CSS/JS；上游已压缩的透传）。
- 去掉 `.222` 备份；`proxy_connect_timeout 2s`（Pocket 不在时快速 502）。
- HSTS。

### 4.3 防火墙
- 删除 `firewall.dsh_pocket`、`firewall.dsh_pocket2`（DNAT）；保留 `Allow-DSH-Pocket-IPv6`。
- **不再加任何 3081/3082 DNAT**。

### 4.4 看门狗（`/usr/bin/dsh-watchdog.sh`，cron `*/5`）
- nginx / ddns 守护（原逻辑）。
- **端口自动发现（轻量版）**：每轮只探当前端口（1 次 curl，`--connect-timeout 1 -m 3`）；探不通才扫 3081–3084，且扫描 10 分钟节流；漂移则原子改写 upstream + `nginx -t` + reload + syslog。
- `pppoe-wan` 的 IPv6 与 `/etc/dsh-ddns-last` 持续 15 分钟不一致 → 告警并重启 ddns。
- 证书 <14 天告警（每小时一次）。
- 单实例锁（`/var/lock/dsh-watchdog.lock`，5 分钟可抢占）。
- ★ 探测必须用 **curl**：PC 未监听端口被 Windows 防火墙静默丢包，BusyBox `wget -T` 不覆盖 connect，会挂到 TCP 超时（当天 watchdog 卡死、进程堆积的根因）。

### 4.5 DDNS（轻量化）
- `check_interval`：5 → **30 分钟**（刷新一次只做本机 `ip` + 一次 DNS 查询；IP 变化由 `95-ddns` 的 ifup hotplug 立即触发，重启/重拨都有事件）。
- `update_cloudflare_dsh.sh`：保留 `last` 短路；新增 **12 小时对账**（GET 一次记录，内容不符或记录被删则修复）。
- `retry_max_count=0`、`ttl=60`、`proxied=false` 不变。

### 4.6 文档/工具
- `tools/deploy_dsh_entry.py`：路由器侧一键幂等部署（推文件 + 删 DNAT + 调 DDNS/cron + reload + 自检）。
- 更新 `04-代理-nikki/dsh-pocket-ipv6/{nginx.conf,upstream.conf,init.d-dsh-nginx,dsh-watchdog.sh,update_cloudflare_dsh.sh,restore-after-flash.sh,README.md}`、`AGENTS.md` §5/§7-7/§8。

## 5. 轻量化口径（回应用户要求）

| 项 | 改前 | 改后 | 说明 |
|---|---|---|---|
| DDNS 轮询 | 5 分钟 = **288 次/天** | 30 分钟 = **48 次/天** | 每次仅 `ip -o addr` + 一次 DNS；IP 变化靠 ifup 事件 + 15 分钟 watchdog 兜底 |
| watchdog | 2 分钟 = 720 次/天 | 5 分钟 = **288 次/天** | 每次：pidof/pgrep + 1 次 LAN curl（~5ms）+ ip addr；证书检查 1 次/小时 |
| 端口扫描 | 无 | 仅当前端口失败时，10 分钟最多一次（3 个候选 × 1s） | 正常状态只 1 个 TCP 连接/5 分钟 |
| CF API | 仅 IP 变化时 | IP 变化时 + 12h 1 次 GET | 约 2 次/天 |

## 6. 验证数据（外网 VPS）

```
GET https://dsh.290490.xyz:3081/   → HTTP/2 200  (TLS1.3, 证书校验 OK)
TTFB 0.31s / 第二次 0.22s；gzip 后 2074 B
POST /pocket-login                 → 302 + cookie
GET /api/remote.mux + Upgrade      → 101 Switching Protocols（带 DSH 会话 cookie）
/assets/index-*.js                 → Cache-Control: public, max-age=31536000, immutable + gzip
端口自愈：上游改 3099 → watchdog 5 秒内改回 3082 + reload
DDNS：模拟 last=旧值 → PUT 成功；verify=0 对账 → 仅 GET、不 PUT
nft：dstnat_wan 无 3081/3082；input_wan 3081 计数随访问增长；flowtable=0
```

## 7. 回滚

- `/root/bak-dsh-20261101/`（nginx.conf、upstream.conf、init、watchdog、ddns 脚本、firewall/ddns uci/export、last 文件）。
- PC：`settings.json.bak-20261101`，删 `proxyPort` 后重启 DSH。
- 仓库：git 可回滚。

## 8. 后续建议（未做）

1. **纯 IPv4 兜底**：保留 DSH 内置命名隧道 `dsh.trustreachclf.com`（Cloudflare 中转，慢）；仅在没有 IPv6 的 WiFi 下临时开启。Cloudflare Zero Trust 里确认其 Public Hostname 的 Service 指向 `http://127.0.0.1:3081`。
2. **PIN 强度**：当前 8 位数字，建议改 12–16 位字母数字（设置 → 手机访问 → 自定义密码）。
3. **`dsh_ssh`（2222→PC:22）**：依赖 PC 的 SLAAC 地址，前缀变化即失效，且公网暴露 SSH；建议评估是否保留。
4. **PC 睡眠**：DSH 依赖 PC 常开；如需长期可用，考虑关闭睡眠或 WoL。
