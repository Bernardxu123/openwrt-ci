# DSH 手机端 IPv6 直连（路由器 DDNS + Cloudflare AAAA）

> 建立日期：**2026-10-27**｜目标：手机在外网用 `https://dsh.290490.xyz:3081` 直接访问家里 PC 上的 DeepSeek Harness（DSH Pocket），不再依赖 cloudflared 隧道。

## 1. 链路

```
手机(IPv6) ──TLS──▶ dsh.290490.xyz
                    │ Cloudflare 权威 DNS（DNS-only，非代理）
                    ▼ AAAA: 2408:820c:8200:4ec4:e950:9581:675a:2ef2（路由器 pppoe-wan）
              路由器 192.168.31.1
                    │ nginx 1.26.3  listen [::]:3081 ssl（Let's Encrypt 证书）
                    │ Host 强制改写为 dsh.290490.xyz（防 IP 直连绕过 PIN）+ WebSocket 透传
                    ▼ HTTP/1.1
              PC 192.168.31.218:3081（DSH Pocket 反代，另有 .222 备份）
                    ▼
              dsh web 127.0.0.1:64509
```

- **DDNS**：路由器 `ddns-scripts`（uci 段 `ddns.dsh_ipv6`，enabled=1，每 5 分钟检查一次），自定义更新脚本 `/usr/lib/ddns/update_cloudflare_dsh.sh` 调 Cloudflare API v4 维护 AAAA。
- **AAAA 指向路由器 WAN 的 IPv6**（`pppoe-wan`），因此只有"一个"动态变量；LAN 前缀/PC 地址变化都不影响。
- **端口 3081**：实测运营商封禁入站 80/443（超时），高端口正常。
- **TLS**：acme.sh（Let's Encrypt，DNS-01 via Cloudflare API）签发，自动续期；证书路径 `/etc/dsh-nginx/cert/`。

## 2. 关键文件（路由器）

| 路径 | 作用 |
|---|---|
| `/etc/config/ddns` | uci 段 `dsh_ipv6`（enabled=1，domain/lookup_host=dsh.290490.xyz，ip_source=interface，ip_interface=pppoe-wan，update_script=...） |
| `/usr/lib/ddns/update_cloudflare_dsh.sh` | Cloudflare AAAA 更新脚本（见本目录同名文件） |
| `/etc/cf-dns.token` | Cloudflare API Token（600，权限 Zone:Read + DNS:Edit，作用域 290490.xyz） |
| `/etc/dsh-ddns-last` | 最近一次成功推送的 IPv6（缓存短路，避免 fake-IP 导致的 5 分钟一次 API 空打） |
| `/etc/dsh-cf-zone.id` / `/etc/dsh-cf-record.id` | zone id / AAAA record id 缓存 |
| `/etc/dsh-nginx/nginx.conf` | nginx 反代配置（见本目录同名文件） |
| `/etc/dsh-nginx/cert/dsh.key` / `dsh.fullchain.pem` | LE 证书（acme.sh 安装） |
| `/etc/init.d/dsh-nginx` | 独立 procd 服务（**nginx-ssl 包自带 init 已 disable**，避免其 uci 配置抢占 80/443） |
| `/etc/acme.sh/` | acme.sh 3.1.7（含 dnsapi/dns_cf.sh 钩子） |
| `/etc/crontabs/root` | `17 3 * * * /etc/acme.sh/acme.sh --cron --home /etc/acme.sh` |
| `/etc/sysupgrade.conf` | 已加 keep：`/etc/dsh-nginx/`、`/etc/init.d/dsh-nginx`、`/etc/rc.d/S99dsh-nginx`、`/usr/lib/ddns/update_cloudflare_dsh.sh`、`/etc/cf-dns.token`、`/etc/dsh-ddns-last`、`/etc/dsh-cf-zone.id`、`/etc/dsh-cf-record.id`、`/etc/acme.sh/`、`/etc/dsh-nginx/cert/`、`/etc/crontabs/root` |

## 3. 防火墙

uci firewall rule（`/etc/config/firewall`，`Allow-DSH-Pocket-IPv6`）：

```
family=ipv6  src=wan  proto=tcp  dest_port=3081  target=ACCEPT
```

即：只放行 wan 侧 IPv6 到**路由器自身**的 tcp/3081，其余入站保持 REJECT。备份：`/etc/config/firewall.bak-20261027`。

## 4. 安全设计（重要）

DSH Pocket 的 `classifyHost()` 把**裸 IPv6 / 未知 Host 当成 loopback（免密）**。如果直接暴露 3081 且不做 Host 改写，任何人解析 AAAA 拿到 IP 后用 IP 直连就能免密进 DSH（等于远程代码执行）。

因此 nginx 对所有请求强制 `proxy_set_header Host dsh.290490.xyz;`，pocket 一律按 `public` 处理 → 强制公网 PIN（默认 30 天 cookie，进程重启失效）。

实测：
- 正常域名访问 → 登录页（PIN 表单）
- 用 `Host: [裸 IPv6]` 伪造访问 → **仍是登录页**（无法绕过）

## 5. 家里 WiFi 访问（已处理 fake-IP）

本机 DNS 由 nikki(mihomo) 接管，默认对外域名返回 fake-IP（`2001:2::/64`），手机在家用域名会绕代理一圈。已把 `dsh.290490.xyz` 加进 nikki profile：

- `/etc/nikki/profiles/openclash-20261022.yaml`
  - 第 314 行：`fake-ip-filter` 增加 `- DOMAIN,dsh.290490.xyz,real-ip`
  - 第 394 行：`rules` 增加 `- DOMAIN,dsh.290490.xyz,🎯 直连`
- 备份：`/root/bak-dsh-20261027/openclash-20261022.yaml.bak`
- 生效方式：`/etc/init.d/nikki restart`（本次已执行，配置校验 `mihomo -d /etc/nikki/run -t` 通过）

## 6. 验证记录（2026-10-27，外部 VPS 161.118.196.196）

| 项目 | 结果 |
|---|---|
| 外部 DNS | `dig AAAA dsh.290490.xyz @1.1.1.1` → `2408:820c:8200:4ec4:e950:9581:675a:2ef2` ✅ |
| HTTPS 登录页 | `curl https://dsh.290490.xyz:3081/` → 200，`ssl_verify_result=0`，页面含 PIN 输入框 ✅ |
| 证书 | `CN=dsh.290490.xyz`，issuer `Let's Encrypt YE1`，2026-10-26 → 2027-01-24 ✅ |
| 明文 HTTP | 同端口 http 访问 → 400（仅 TLS）✅ |
| PIN 登录 | `POST /pocket-login token=29049087` → 302 `/?dsh-pocket-auth=1` + `dsh_pocket_token` cookie ✅ |
| WebSocket | `GET /api/remote.mux` Upgrade → **101 Switching Protocols** ✅ |
| Host 绕过测试 | `Host: [裸IPv6]` → 仍登录页 ✅ |
| 家内 PC 域名访问 | PC 解析真实 IPv6，`https://dsh.290490.xyz:3081/` → 200 ✅ |
| 80/443 入站 | 运营商封禁（超时），故用 3081 |

## 7. 回滚

```sh
# 1) 停用直连入口
/etc/init.d/dsh-nginx stop && /etc/init.d/dsh-nginx disable
# 2) 关 DDNS
uci set ddns.dsh_ipv6.enabled=0 && uci commit ddns && /etc/init.d/ddns restart
# 3) 删 Cloudflare 记录（或在面板手动删 dsh AAAA）
# 4) 防火墙撤销
uci delete firewall.@rule[<idx>]  # 或恢复 /etc/config/firewall.bak-20261027
# 5) 恢复 nikki profile
cp /root/bak-dsh-20261027/openclash-20261022.yaml.bak /etc/nikki/profiles/openclash-20261022.yaml
/etc/init.d/nikki restart
# 6) 回退 PC 侧隧道（如果需要）
#    PowerShell(管理员):
#    Set-Service Cloudflared -StartupType Automatic; Start-Service Cloudflared
#    再把 C:\Users\29049\.dsh\dsh-pocket\tunnel-auto.json.bak-20261027 改名回 tunnel-auto.json（quick 隧道自动恢复用）
```

## 8. 注意 / 已知边界

- 固件仍为 **OpenWrt 25.12.3（R26.10.25）**，nginx/libpcre2/libxml2-16 来自 **24.10.6 feed**（实测可运行）；**整机升级后需重装 nginx-ssl** 并重建 `/etc/dsh-nginx`（本目录文件 + README）。
- `nginx-ssl` 包自带 init 已 disable；其 cron `nginx-util check_ssl`（每年 12/12）只维护自签 `_lan` 证书，与本服务无关。
- ddns-scripts 的 `lookup_host` 校验会被 fake-IP 干扰（永远显示需要更新）；靠脚本内 `/etc/dsh-ddns-last` 缓存短路，日志每 5 分钟一条"IP 未变化，跳过 API"属正常。
- 公网 PIN 是 **8 位纯数字（29049087）**，建议在 DSH 设置 → 手机访问 → 自定义密码改成 **12–16 位字母数字混合**（速率限制：同 IP 连错 5 次锁 60 秒；因为 nginx 反代，pocket 看到的来源统一是 192.168.31.1，所以是全局锁）。
- cloudflared 公网隧道已停：公网隧道实际是 **Windows 服务 `Cloudflared`（Auto，指向 `C:\ProgramData\cloudflared\token`）**，已 `Stop-Service` + `Set-Service -StartupType Disabled`（当前 0 进程）；另删除 `tunnel-auto.json`（备份 `.bak-20261027`）防止 DSH 重启拉 quick 隧道；`settings.json` 里 named tunnel 配置保留，随时可恢复（见 §7 第 6 步）。
- 若路由器 PPPoE 重拨导致 WAN IPv6 变化：DDNS 在 ≤5 分钟内更新，AAAA TTL=60s。
