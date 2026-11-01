# DSH 手机端 IPv6 直连（路由器 DDNS + Cloudflare AAAA）

> 建立日期：**2026-10-27**｜最近重构：**2026-11-01**（修端口漂移/DNAT 抢流量 + HTTP/2 + 缓存 + DDNS 降频）
> 目标：手机在外网用 `https://dsh.290490.xyz:3081` 直接访问家里 PC 上的 DeepSeek Harness（DSH Pocket），不依赖 cloudflared 隧道。

## 1. 链路

```
手机(IPv6) ──TLS1.3/HTTP2──▶ dsh.290490.xyz
                    │ Cloudflare 权威 DNS（DNS-only，非代理）
                    ▼ AAAA: 2408:820c:8200:44ef:b0ad:28b5:22a5:bb66（路由器 pppoe-wan）
              路由器 192.168.31.1
                    │ nginx 1.26.3  listen [::]:3081 ssl（Let's Encrypt）+ http2
                    │ Host 强制改写为 dsh.290490.xyz + WebSocket 透传
                    │ 上游 = /etc/dsh-nginx/upstream.conf（由 watchdog 维护，实际 192.168.31.218:3082）
                    ▼ HTTP/1.1 keepalive
              PC 192.168.31.218:<Pocket 实际端口>（当前 3082；DSH 重启后可能回 3081）
                    ▼
              dsh web 127.0.0.1:64509
```

- **DDNS**：`ddns.dsh_ipv6`（每 **30 分钟**轮询 + `95-ddns` 在 ifup 时立即触发；IPv6 只在重拨/重启变），脚本 `/usr/lib/ddns/update_cloudflare_dsh.sh` 调 Cloudflare API v4 维护 AAAA，并每 **12 小时**对账一次线上记录。
- **AAAA 指向路由器 WAN 的 IPv6**（`pppoe-wan`），因此只有"一个"动态变量；PC 的 IPv6 不参与（RA/SLAAC 前缀随重拨变）。
- **端口 3081**：实测运营商封禁入站 80/443（超时），高端口正常。
- **TLS**：acme.sh（Let's Encrypt，DNS-01 via Cloudflare API）签发，自动续期；证书路径 `/etc/dsh-nginx/cert/`。

## 2. 关键文件（路由器）

| 路径 | 作用 |
|---|---|
| `/etc/config/ddns` | uci 段 `dsh_ipv6`（enabled=1，`check_interval=30`，`retry_max_count=0`，`ip_source=interface` + `ip_interface=pppoe-wan`） |
| `/usr/lib/ddns/update_cloudflare_dsh.sh` | Cloudflare AAAA 更新脚本（含 12h 对账） |
| `/etc/cf-dns.token` | Cloudflare API Token（600，Zone:Read + DNS:Edit，作用域 290490.xyz） |
| `/etc/dsh-ddns-last` | 最近一次成功推送的 IPv6（缓存短路） |
| `/etc/dsh-ddns-last-verify` | 上次对账时间戳（epoch，12h 窗口） |
| `/etc/dsh-cf-zone.id` / `/etc/dsh-cf-record.id` | zone id / AAAA record id 缓存 |
| `/etc/dsh-nginx/nginx.conf` | nginx 反代（HTTP/2 + gzip + `/assets/` 强缓存 + keepalive） |
| `/etc/dsh-nginx/upstream.conf` | 上游片段（watchdog 自动维护），如 `server 192.168.31.218:3082 max_fails=2 fail_timeout=10s;` |
| `/etc/dsh-nginx/port` | 当前探测到的 Pocket 端口（watchdog 状态） |
| `/etc/dsh-nginx/cert/dsh.key` / `dsh.fullchain.pem` | LE 证书（acme.sh 安装） |
| `/etc/init.d/dsh-nginx` | 独立 procd 服务（**nginx-ssl 包自带 init 已 disable**） |
| `/usr/bin/dsh-watchdog.sh` | cron `*/5`：nginx/ddns 守护、端口自动发现、IPv6 一致性、证书到期告警（单实例锁） |
| `/etc/acme.sh/` | acme.sh 3.1.7（含 dnsapi/dns_cf.sh 钩子） |
| `/etc/crontabs/root` | `17 3 * * *` acme 续期；`*/5 * * * * /usr/bin/dsh-watchdog.sh` |
| `/etc/sysupgrade.conf` | 已加 keep：`/etc/dsh-nginx/`（含 upstream.conf/port）、`/etc/init.d/dsh-nginx`、`/usr/bin/dsh-watchdog.sh`、`/etc/acme.sh/`、`/etc/cf-dns.token`、`/etc/dsh-ddns-last`、`/etc/dsh-cf-*.id`、`/etc/crontabs/root`、`/usr/lib/ddns/update_cloudflare_dsh.sh`、`/usr/bin/dsh-restore.sh` |

PC 侧（DSH Pocket）设置：`%USERPROFILE%\.dsh\dsh-pocket\settings.json` 增加 `"proxyPort": 3081`（插件只在启动时读取；下次 DSH 重启生效）。

## 3. 防火墙

```
Allow-DSH-Pocket-IPv6：family=ipv6  src=wan  proto=tcp  dest_port=3081  target=ACCEPT
```

★ **不要加 DNAT**：2026-11-01 发现曾有两跳 `fw4` redirect（wan 3081/3082 → PC 的 IPv6），会抢在 nginx 之前把流量劫持到 PC；Pocket 只监听 `0.0.0.0`（IPv4），IPv6 永远连不上，而且绕过了 TLS/Host 改写。已删除（`/root/bak-dsh-20261101/`）。

## 4. 安全设计

- DSH Pocket 的 `classifyHost()` 把**裸 IPv6 / 未知 Host** 当 loopback（免密），所以 nginx 对所有请求强制 `proxy_set_header Host dsh.290490.xyz;` ⇒ pocket 一律按 `public` 处理、强制公网 PIN。
- 实测（2026-11-01）：PIN 登录 `POST /pocket-login` → 302；未带 cookie 的 API/WS → 401；带 DSH 会话 cookie 的 `/api/remote.mux` Upgrade → **101**。
- 入口 = TLS + PIN（8 位，建议改 12–16 位字母数字）；因为反代，pocket 看到的源 IP 统一为路由器 LAN 地址，5 次错锁 60s 是**全局锁**。

## 5. 家里 WiFi 访问（已处理 fake-IP）

`/etc/nikki/profiles/openclash-20261022.yaml`：
- `fake-ip-filter`：`- DOMAIN,dsh.290490.xyz,real-ip`
- `rules`：`- DOMAIN,dsh.290490.xyz,🎯 直连`

## 6. 验证记录（2026-11-01，外部 VPS 161.118.196.196）

| 项目 | 结果 |
|---|---|
| AAAA | `2408:820c:8200:44ef:b0ad:28b5:22a5:bb66`（= pppoe-wan） |
| HTTPS + ALPN | `HTTP/2 200`，TLS1.3，证书 CN 正确、校验 OK |
| 时延 | 首包 TTFB **0.31s**，第二次 **0.22s**（新加坡→联通家宽 IPv6） |
| gzip | HTML 42670 B → **2074 B** |
| 静态缓存 | `/assets/*` → `Cache-Control: public, max-age=31536000, immutable` + gzip |
| 登录 | `POST /pocket-login` → 302 + `dsh_pocket_token` cookie |
| WebSocket | 带 DSH 会话 cookie `/api/remote.mux` → **101 Switching Protocols** |
| DDNS 跟随 | CF `modified_on` 2026-10-31T09:46:10Z、`/etc/dsh-ddns-last` 17:45（本地）⇒ 换 IP 后 1 分钟内更新；comment=`dsh-pocket-router-ddns` |
| DDNS 强制更新 | 手动模拟（last 写旧值）→ 脚本 PUT 成功、last/verify 回写 |
| DDNS 对账 | verify=0 时脚本只 GET、内容一致则跳过 PUT |
| 端口自愈 | 上游故意改成 3099 → watchdog **5 秒**内探测并改回 3082 + reload |
| flowtable | 0（维持 §7-1 铁律） |

## 7. 回滚

```sh
# 路由器：恢复备份
cp /root/bak-dsh-20261101/nginx.conf /etc/dsh-nginx/nginx.conf
cp /root/bak-dsh-20261101/init.d-dsh-nginx /etc/init.d/dsh-nginx
cp /root/bak-dsh-20261101/dsh-watchdog.sh /usr/bin/dsh-watchdog.sh
cp /root/bak-dsh-20261101/update_cloudflare_dsh.sh /usr/lib/ddns/update_cloudflare_dsh.sh
cp /root/bak-dsh-20261101/firewall.uci /etc/config/firewall
cp /root/bak-dsh-20261101/ddns.uci /etc/config/ddns
/etc/init.d/firewall reload; /etc/init.d/ddns restart; /etc/init.d/dsh-nginx restart
# PC：删掉 settings.json 里的 proxyPort 后重启 DSH
```

## 8. 注意 / 已知边界

- **Pocket 端口会漂**：DSH 默认 3081，启动时被占会 `+1..+9`；watchdog 5 分钟内自动纠正。若要立刻确认：`cat /etc/dsh-nginx/port`。
- **探测必须用 curl**：PC 未监听端口会被 Windows 防火墙静默丢包，BusyBox `wget -T` 不覆盖 connect，会挂到 TCP 超时（2026-11-01 踩坑）。
- **reload 后自检**：端口变更 reload 后做一次本地 HTTPS 探针（`Host` + `[::1]:3081`），非 200/302 自动 `restart` —— OpenSSL 偶发 `SSL_CTX_new` emerg 会让 reload 静默失效、旧 worker 继续用旧上游。
- **DDNS 频率**：IP 只在重拨/重启变，轮询 30 分钟 + ifup 事件触发 + 12h 对账；`retry_max_count=0`。
- **刷机（sysupgrade）后**：nginx-ssl/libpcre2/libxml2-16 包会丢 → `sh /usr/bin/dsh-restore.sh`（会补齐 upstream.conf/port）。CF 链路：`python tools/restore_cf_after_flash.py`。
- **公网只有 AAAA**：纯 IPv4 网络（部分酒店/公司 WiFi）打不开；兜底用 DSH 内置命名隧道 `dsh.trustreachclf.com`（Cloudflare 边缘中转，较慢，按需开启）。
- 证书 acme reloadcmd 已配 `/etc/init.d/dsh-nginx reload`。

## 9. 故障修复记录

**2026-10-27**：重拨后入口打不开，误判 DDNS；实际是 `/var` tmpfs 丢 `/var/lib/nginx`，nginx 退出。修复：init 建目录 + 看门狗 + `retry_max_count=0`。

**2026-11-01**：公网 502/超时。两条根因：① DSH 16:11 重启后 Pocket 漂到 3082，nginx 仍指 3081（且 `.222` 死备份让 502 拖到 8 秒）；② 两条未记录的 DNAT 抢流量，而 Pocket 只监听 IPv4 ⇒ 外网必超时。修复：删 DNAT、PC 固定 `proxyPort`、watchdog 自动发现端口、nginx 加 HTTP/2/缓存/gzip/keepalive/快速 502；DDNS 降频到 30 分钟并加 12h 对账。
