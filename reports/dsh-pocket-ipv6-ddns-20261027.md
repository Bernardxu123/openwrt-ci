# DSH 手机端 IPv6 直连 — 落地记录（2026-10-27）

## 目标

用户要求：**路由器 DDNS 开启 + Cloudflare + 290490.xyz + IPv6 绑定**，让手机在外网直接访问电脑上的 DeepSeek Harness（DSH Pocket），替代 cloudflared 隧道。

## 结论

已完成并端到端验证。手机地址：**`https://dsh.290490.xyz:3081`**（公网 PIN：`29049087`，建议改强）。

## 实际架构

```
手机 IPv6 ──TLS(LE)──▶ dsh.290490.xyz ──AAAA(DNS-only)──▶ 2408:820c:8200:4ec4:e950:9581:675a:2ef2
                                                             │ 路由器 pppoe-wan
                                                             ▼
                                          nginx [::]:3081 ssl（Host→dsh.290490.xyz, WS 透传）
                                                             ▼
                                          PC 192.168.31.218:3081（DSH Pocket；.222 备份）
                                                             ▼
                                          dsh web 127.0.0.1:64509
```

关键决策：
1. **AAAA 指向路由器 WAN IPv6**（不是 PC 地址）。PC 的 IPv6 是 RFC7217 稳定隐私地址，前缀变化后整段变，不适合做 DDNS 目标；指向路由器后"唯一动态变量"就是 pppoe-wan 地址。
2. **必须经 nginx 反代并改写 Host**：DSH Pocket `classifyHost()` 把裸 IPv6 Host 判为 loopback（免密）。若不改写，任何人从 DNS 拿到 IP 后 `https://[ip]:3081` 即免密进入 DSH（远程代码执行风险）。实测改写后 IP 直连也只能看到 PIN 登录页。
3. **端口 3081**：实测运营商封禁入站 80/443（外部探测超时），高端口正常。
4. **TLS 用 Let's Encrypt DNS-01**（Cloudflare API），因为 HTTP-01 需要入站 80。
5. **家里 WiFi 也要能用**：nikki fake-IP 会把该域名解析成 `2001:2::x` 走代理，已加 real-ip + 直连规则。

## 变更清单

### 路由器 192.168.31.1（OpenWrt 25.12.3 / R26.10.25，aarch64）

| 类别 | 内容 |
|---|---|
| 安装包 | `nginx-ssl 1.26.3-r1`（来自 24.10.6 feed）、`libpcre2`、`nginx-ssl-util`、`libxml2-16`；`nginx` 包自带 init **已 disable** |
| 自建服务 | `/etc/dsh-nginx/nginx.conf` + `/etc/init.d/dsh-nginx`（procd，S99/K10 自启），监听 `[::]:3081 ssl` |
| 证书 | `/etc/dsh-nginx/cert/dsh.fullchain.pem` / `dsh.key`（acme.sh 安装，reloadcmd 已设） |
| DDNS | uci `ddns.dsh_ipv6`（enabled=1，每 5 min，`ip_source=interface` + `ip_interface=pppoe-wan`）；脚本 `/usr/lib/ddns/update_cloudflare_dsh.sh`；token `/etc/cf-dns.token`(600) |
| DDNS 缓存 | `/etc/dsh-ddns-last`、`/etc/dsh-cf-zone.id`（bd8e167c…）、`/etc/dsh-cf-record.id`（d2548847…） |
| 防火墙 | `Allow-DSH-Pocket-IPv6`：family=ipv6 src=wan proto=tcp dest_port=3081 ACCEPT（备份 `/etc/config/firewall.bak-20261027`） |
| ACME | `/etc/acme.sh/`（3.1.7 + `dnsapi/dns_cf.sh`）、cron `17 3 * * * ... --cron --home /etc/acme.sh` |
| DNS 例外 | `/etc/nikki/profiles/openclash-20261022.yaml`：`fake-ip-filter` + `- DOMAIN,dsh.290490.xyz,real-ip`；`rules` + `- DOMAIN,dsh.290490.xyz,🎯 直连`（备份 `/root/bak-dsh-20261027/`） |
| 持久化 | `/etc/sysupgrade.conf` 追加 11 项（详见 `dsh-pocket-ipv6/README.md` §2） |

### PC（DSH 侧，未改网络）

- 停掉 cloudflared 隧道：公网隧道实际是 **Windows 服务 `Cloudflared`（Auto）**，已 `Stop-Service` + `Set-Service -StartupType Disabled`（0 进程）；`%USERPROFILE%\.dsh\dsh-pocket\tunnel-auto.json` 备份为 `.bak-20261027` 后删除（防止 DSH 重启自动拉起 quick/named 隧道）。**教训：只杀进程会被服务自动拉起，必须停服务**。
- 无端口转发/Windows 防火墙改动（nginx 走 IPv4 到 192.168.31.218:3081）。

### Cloudflare

- `dsh.290490.xyz` **AAAA = 2408:820c:8200:4ec4:e950:9581:675a:2ef2**，`proxied=false`，TTL 60。
- 使用 zone 级 API Token（Zone:Read + DNS:Edit，作用域 290490.xyz），仅存路由器 `/etc/cf-dns.token`。

## 验证证据（外部 VPS 161.118.196.196，2026-10-27 08:24~08:28）

| # | 测试 | 结果 |
|---|---|---|
| 1 | `dig +short AAAA dsh.290490.xyz @1.1.1.1` | `2408:820c:8200:4ec4:e950:9581:675a:2ef2` |
| 2 | `curl https://dsh.290490.xyz:3081/` | 200，`ssl_verify_result=0`，含 `name="token"` 登录表单 |
| 3 | `openssl s_client` 证书 | `CN=dsh.290490.xyz` / issuer `Let's Encrypt YE1` / 2026-10-26→2027-01-24 |
| 4 | `curl http://dsh.290490.xyz:3081/` | 400（仅 TLS，无明文） |
| 5 | `POST /pocket-login token=29049087` | 302 → `/?dsh-pocket-auth=1`，`Set-Cookie: dsh_pocket_token=…` |
| 6 | `GET /api/remote.mux` + Upgrade | **101 Switching Protocols**（WebSocket 透传 OK） |
| 7 | `Host: [裸IPv6]` 伪造 | 仍返回登录页（PIN 不能被绕过） |
| 8 | 家内 PC 访问域名 | 解析真实 IPv6，200 |
| 9 | 80/443 入站 | 超时（运营商封禁） |
| 10 | DDNS 日志 | `cloudflare: dsh.290490.xyz AAAA -> … 更新成功`；后续周期 `IP 未变化，跳过 API` |

## 安全

- 入口 = TLS + DSH Pocket PIN（8 位数字，5 次错锁 60s；因反代，pocket 看到的源 IP 统一为 192.168.31.1，故为全局锁）。
- IP 直连无法绕过（Host 改写）。
- **建议**：把 PIN 改为 12–16 位字母数字混合（DSH 设置 → 手机访问 → 自定义密码）；长期可考虑 Cloudflare Access / 只放行自己常用网段（IPv6 前缀较稳定时）。
- Token 只在路由器 600 文件；如需轮换，CF 面板 Revoke 后替换 `/etc/cf-dns.token` 即可（`/etc/dsh-cf-*.id` 无需改）。

## 已知边界 / 维护

- 运营商封 80/443：不要试图改端口到 443，会不通。
- 固件升级后需重装 `nginx-ssl`（来自 24.10.6 feed）并恢复 `/etc/dsh-nginx`（本仓库 `dsh-pocket-ipv6/` 内有源文件）。
- DDNS 的 `lookup_host` 校验受 fake-IP 影响会一直"需要更新"，脚本用 `/etc/dsh-ddns-last` 短路，不会空打 API。
- PPPoE 重拨 → WAN IPv6 变化 → ≤5 分钟 DDNS 更新（TTL 60s）。
- 若 PC 改回 WiFi（.222），nginx upstream 有 backup，但需该地址在线。

## 回滚

见 `dsh-pocket-ipv6/README.md` §7（停服务/关 DDNS/恢复 nikki/恢复隧道）。
