# 家庭网络环境 · 运维手册（AI 必读）

> **2026-11-10 20:05 nikki 配置审查 + 去重修复（规则 76→74；sniffer `port`→`ports` 已修；dsh AAAA 抖动根因已解）**：口径「低风险修复并验证」，共 8 项。① profile 删 2 条被 `DOMAIN-SUFFIX,290490.xyz → 🎯 直连` **同目标完全覆盖**的死规则（`DOMAIN,xx.290490.xyz` / `DOMAIN,dsh.290490.xyz`；实测两域无 A 记录、`dsh` 只有 AAAA 且 IPv6 不代理 ⇒ 纯死条），规则 **76→74**；② 头注释 6 处错值（`port 7890`/`socks 7891`/`redir 7892`/`mixed 7893`/`tproxy 7895`/`bind-address`/`external-controller 0.0.0.0:9090`）全部改成 UCI 真实值（8080/1080/7891/7890/7892、mixin **不下发** bind-address、API `[::]:9090`）；③ 删 UCI 地雷 `@nameserver_policy[1]`（`geolocation-!cn → https://1.1.1.1 / 8.8.8.8`，开关=0 一直 inert，一旦打开就踩 §7-4）⇒ section 2→1；④ `uci set nikki.mixin.mixin_file_content=1` 让 **`/etc/nikki/mixin.yaml` 从死文件变成第三配置面**，并在其中补 `sniffer.sniff.{HTTP,TLS}.ports`（mihomo 1.19.33 结构 `RawSniffingConfig{ Ports []string \`yaml:"ports"\` }`，wiki `/config/sniff/` 示例 `TLS: ports: [443,8443]` 证实；旧 `port` 键保留、被忽略、无害）⇒ **8080/8443 嗅探首次真正生效**；⑤ `🛡️ 稳定固定` 从 Hy2 选回 `🇸🇬 新加坡-自建TLS`（delay 187ms；Hy2 bulk HTTPS 失败，只作备用）；⑥ **dsh AAAA 抖动根因**：`dsh.290490.xyz`（DDNS，只有 AAAA）原走 `nameserver-policy rule-set:zdcn → 192.168.31.1` → 联通 ISP 多个缓存实例不同步（debug 实证 `[DNS] resolve dsh.290490.xyz AAAA from udp://192.168.31.1:53` 回旧前缀，同一时刻 `223.5.5.5` 已是新前缀）⇒ `dsh-dns-guard` 每 15 分钟比对失败 → reload 无效 → **重启 nikki（15s 全代理中断**，19:15 实测）；已在 profile `nameserver-policy` 首位加 `"dsh.290490.xyz" → 223.5.5.5 / 119.29.29.29`（TTL 60，其余 290490 域名仍走 dnsmasq），实测解析源变 `udp://223.5.5.5:53`、AAAA == WAN、外网入口 `curl -6 dsh:3081` **200/1.22s**（改前 000 超时）；⑦ `/usr/bin/dsh-dns-guard.sh` 加第一档 `POST /cache/dns/flush`（API 实测 204）→ 复查 → 再 reload → 最后才 restart（1449B→1882B）；⑧ 本地仓库 profile/UCI/run 快照与 AGENTS 同步。验证：`mihomo -t` 过、规则 **74**/组 22/provider 4、core.log 0 error、`app.log` `Hijack successful`、运行时 `sniff.*.ports` 出现、DNS 矩阵不变（境外 A=`198.18.x`+AAAA 空、国内真实、`dsh` AAAA=WAN、`tablet.lan`=.122）、6 站点全 200（中位 taobao 0.06 / youtube 0.31 / chatgpt 0.41 / github 0.24 / opencode 0.27 / learn 0.63，较改前 0.057/0.400/0.380/0.177/0.216/0.842 不劣；20:00 一轮整体偏高经复测属晚高峰抖动，同刻 taobao 也变慢）、**运行时配置 diff 仅 7 行**（+dsh policy 3 行 +ports 2 条 − 死规则 2 条）、VmRSS 96.5→85.0MB / MemAvailable 109MB。备份 `/root/bak-nikki-review-20261110/`，报告 `reports/nikki配置审查与去重优化-20261110.md`。★ 后续注意：**别用 LuCI「混入配置」整页保存**（会把 `mixin_file_content` 复位成 0，`ports` 再次失效）；别在 LuCI 打开「fake-ip 过滤 / DNS 上游 / DNS 策略」开关（会整体替换 profile 的 32 条白名单与上游）。
> **2026-11-10 17:15 主路由升 QWRT R26.11.10（内核 5.4.302）＋「软件流量卸载」修复（真因：flowtable 设备数 10 > 7）**：升级把 `/usr/share/ucode/fw4.uc` 换回厂商新文件，2026-11-06 打的「设备裁剪」补丁丢失；而当时的 cron `@reboot` **从未执行过**（busybox crond 1.35 不支持 `@reboot`，日志里没有任何该任务记录）⇒ 选「软件流量卸载」时 fw4 生成 10 个设备的 flowtable（`br-lan lan1-4 pon0 pon0.995 pppoe-wan ra0 rai0`），`nft` 报 `File too large`、reload 中止并**保留上一份硬件 ruleset**（7 个物理口 + `flags offload`）⇒ 界面显示已切换、实际一直跑硬件卸载（实测 PC 侧 NIC 计数器 630–671 Mbps）。处置：重打补丁并改为**开机钩子** `/etc/init.d/dsh-fw4-offload-fix`（`START=18`，早于 firewall `S19`；脚本带兜底：锚点失效或设备数仍 >7 就自动把 offload 关成「无」，保证 fw4 一定能加载）；`/usr/bin/dsh-fw4-offload-fix.sh` 增加 `--no-reload`，删掉那条无效 `@reboot`。`firewall restart` 现 rc=0，flowtable = `{ br-lan, pon0.995, pppoe-wan }`（无 `flags offload`），`[OFFLOAD]` 正常增长；同一 24 流多源实测 **硬件 630–671 Mbps → 软件 948–968 Mbps（PC 1GbE 线速上限 968）**。另：`flow_offloading_hw` 显式固定 `0`；升级后又丢 `nginx-ssl`（`/usr/sbin/nginx` 不存在、dsh-nginx crash loop）→ `sh /usr/bin/dsh-restore.sh` 已恢复（3081 监听、local https 200）；删掉 4 条指向不存在路径的 include（openclash、zerotier×3）；修 `dsh-watchdog` / `update_cloudflare_dsh.sh` 的 IPv6 前导零比较（`0ad3` vs `ad3` 曾每 15 分钟误判并重启 ddns）。备份 `/root/bak-offload-20261110/`，详见 `reports/固件升级R26.11.10-软件卸载修复-20261110.md`。
> **2026-11-10 14:50 Google 单独成组 `🔐 Google`（借鉴 liuran001 懒人配置）**：新增 select 组 `🔐 Google`（成员 `🇸🇬 新加坡节点`/`🚀 默认代理`/`🌐 全部节点`/DIRECT，默认 `🇸🇬 新加坡节点 → [乌龟] 🇸🇬 Singapore-AnyTls`），**Google 全站（Gemini / AI Studio / Play / accounts / www / oauth / gstatic）统一一组一 IP**；规则 74→**76**：新增 `GEOSITE,google-gemini → 🔐 Google`（必须排在 `GEOSITE,category-ai-!cn` 之前）、`alkalimakersuite-pa.clients6.google.com → 🔐 Google`，并把 16 条 Play/Gemini 显式域名、`alkalimakersuite-pa.googleapis.com`、`GEOSITE,google` 全部从 `🤖 AI`/`🌐 全部节点` 改指 `🔐 Google`；`🤖 AI` 恢复默认 `🚀 默认代理`（只管非 Google AI）；`🌐 全部节点` 仍钉 `日本-原生01`。**Gemini 节点实测很挑**：`[乌龟] SG AnyTls` 4/4 成功（TTFB 0.62–0.71s）、台湾-住宅2 4/4 但 TTFB 0.51–2.09s、韩国-住宅 3/4，其余（日本原生01/02/03、台湾-住宅/住宅3、越南原生、英国住宅、顺畅 SG 流媒体03、吹雪 SG 移联01、自建TLS）**0–1/4（connect 超时/秒断）** ⇒ 默认选乌龟 AnyTls；修复后 gemini/accounts/play/gstatic 日志全部命中 `🔐 Google[乌龟 SG AnyTls]`，ChatGPT 仍 `GeoSite(category-ai-!cn) → 🤖 AI`。备份 `/root/bak-google-group-20261110/`（初始）与 `/root/bak-google-group-v2/`（收窄成员后）。详见 `reports/Gemini与AIStudio线路诊断-20261110.md` §8。
> **2026-11-10 14:35 Gemini/AI Studio「验证/报错」根因：Google 会话跨区分裂，已统一出口**：mihomo info 日志实测同一 Gemini 会话里 `gemini/aistudio/play.googleapis.com → 🤖 AI → 🚀 默认代理 → ♻️ 新加坡自动（SG，出口 141.11.46.237 / AS401243 Komi LLC 数据中心、Scamalytics Server=Yes）`，而 `accounts.google.com / www.google.com(.hk) / oauthaccountmanager.googleapis.com / mtalk.google.com → GEOSITE,google → 🌐 全部节点 → [顺畅] 🇯🇵日本-原生01（JP）` —— 同一账号 SG/JP 双出口是 Google 风控“Verify it's you/登录循环/地区报错”的直接诱因；叠加两个因素：`♻️ 新加坡自动` 是 url-test（600s 换节点=换 IP）、原 AI 组钉在自建TLS（TLS 1.57s 且 05:41 `connect error: context deadline exceeded`）。处置：`PUT /proxies/🤖 AI {"name":"🌐 全部节点"}` → 全部 Google 域统一走 `[顺畅] 🇯🇵日本-原生01` 单节点单 IP；实测 Gemini TLS 0.18s / TTFB 0.44–0.51s / total 0.8–1.0s、AI Studio TTFB 1.16–1.29s、accounts 0.37s；OpenCode/OpenDesign/YouTube 不受影响。**（13:55 的“AI→默认代理”是中间态，已被本条取代）** 出口刚变，Google 可能仍要求一次验证（清 google.com cookies 或重登后再观察）；若持续，下一步建 `🔐 Google` 专用组（原生/住宅 IP、固定不自动切）并把 AI 与 GEOSITE,google 两条规则都指过去（需改 profile + 重启 nikki ~5s，先备份）。详见 `reports/Gemini与AIStudio线路诊断-20261110.md` §7。
> **2026-11-10 13:55 Gemini/AI Studio 线路修复**：`gemini.google.com` / `aistudio.google.com` 实测命中规则 56 `GeoSite(category-ai-!cn) → 🤖 AI`（**不是默认代理**；`GEOSITE,google` 是更后面的兜底）；当时 `🤖 AI` 被钉在 `🛡️ 稳定固定 → 🇸🇬 新加坡-自建TLS`，Gemini TLS p50 **1.57s** / TTFB p50 **2.24s**，core.log 抓到 `161.118.196.196:8443 connect error: context deadline exceeded`（05:41）；已把 `🤖 AI` 切回 `🚀 默认代理`（`♻️ 新加坡自动 → [顺畅] 🇸🇬新加坡-流媒体02`），实测 Gemini TLS 0.26s / TTFB **0.44–0.49s**、AI Studio TTFB 1.48–1.74s（原 2.28s）；备选 `🌐 全部节点`（日本原生01：AI Studio 1.17s，但单节点且 03:52 有 `dial tcp 16.162.120.212:43134 i/o timeout`）；`🛡️ 稳定固定`/自建TLS 只作备用；详见 `reports/Gemini与AIStudio线路诊断-20261110.md`。
> **2026-11-09 09:00 自编译 7.3.1（CU）试验暂停，主路由回退 CT / QWRT**：CU 已刷 b56（`r0-5501105`）+ honk 配好并跑通（3 个订阅 39 节点、国内直连/国外代理、出口 SG 节点、Doona 面板 `http://192.168.31.1:9527/ui/`、Clash API `:9090` 供 DSH 插件预留）；但**关 flow offload 后吞吐仅 800+ Mbps，而 CT（QWRT R26.11.6 / 5.4.302）软件卸载实测 1022 Mbps**，且 flowtable 与透明代理互斥（honk 必须 offload=0）⇒ 光纤与主路由回退 CT，CU 作为备用/试验机存放。honk 配置细节与 6 条踩坑（bootstrap DNS、8.8.8.8 DoH 400、信息节点过滤、datapath 脏状态需整机重启、offload 冲突、restart 竞态）见 `reports/自编译固件-honk接入与性能结论-20261109.md`；镜像归档 `01-光猫-HG5585F/固件/自编译-7.3.1-{ct,cu}-20261108-b55/`，GitHub releases `fw-20261108-b55-{cu,ct}`（b56 由 CI 自动发布）。回退后 CU 与 CT **不能同时接同一 LAN**（都是 192.168.31.1）。
> **2026-11-08 10:45 DSH 插件「API 线路」MVP 上线**：把 Windows 任务计划里的 `tools/api_route_optimizer.py` 迁进 DSH —— 放置 `sidebar-left`（左栏「API 线路」图标 + 独立主区页面，slot `sidebar.panellist id=api-route` + `main key=api-route`，均已实测 active）；Host 半 canary/full(dry-run/apply)/restore + 8 个 loopback 路由 `/api/api-route/*`，Client 半状态页（两目标卡片、三个按钮、事件日志、设置区）；零 token、无控制台窗口、无 Python 子进程、不写 profile；mihomo secret 存 DSH credentials（记录键 `api-route-optimizer`，不落盘/不回传/不进日志）；实测真实 canary（opencode 200 / OD 401，colo SIN）、full dry-run/apply 均 no-op（与 2026-11-07 fixture 一致），强制 `⚡ OpenCode=DIRECT` 后自动切 `🌐 全部节点`（0.702→0.544s，23%/158ms，colo NRT，bulk 9.6Mbps）并 `恢复默认` 回 `🚀 默认代理`；单测 85/85；**已为路由器换 honk 预留 `RouterBackend` 抽象**（引擎差异集中在 `lib/backends/honk.js`，切 `settings.backend='honk'` + Clash API 地址 + 组名覆盖即可，无需重启 Host）；插件源码 `plugins/dsh-api-route-optimizer/`（`install_bundle` 以 link 方式装进 web profile），报告 `reports/DSH插件-API线路优化-落地报告-20261108.md`；**页面需刷新一次 DSH 才会加载新的左栏入口**；**2026-11-08 已删除 Python 任务 `ApiRouteCanary`/`ApiRouteFull`，脚本/状态归档到 `04-代理-nikki/archive/api-route-python-20261107/`，插件为唯一运行路径；路由器旧备份已清理，仅保留 `/root/bak-api-route-20261107-191719/`。**
> **2026-11-07 19:40 API 线路优化**：`opencode.ai` 从 `🛡️ 稳定固定`（自建 SG TLS，TLS 0.80s / TTFB 1.31s）切到 `🚀 默认代理`（`♻️ 新加坡自动`，TLS 0.26s / TTFB 0.57s，10/10）；`open-design.ai` 独立为 `🎨 OpenDesign`（默认 `♻️ 新加坡自动`，TTFB 0.59–0.70s，不动）；新建 `⚡ OpenCode 池` / `🎨 OpenDesign 池`（各 46 个亚洲候选，脚本选路）；脚本 `tools/api_route_optimizer.py`（canary 30min + 每周日 04:30 full，零 token；20%/80ms 迟滞，OD 在 0.9s 以下要求 30%/150ms）+ `tools/patch_api_route_20261107.py`；规则 74、组 21；备份 `/root/bak-api-route-20261107-191719/`；详见 `reports/API线路优化-20261107.md`。
> 上次更新：**2026-11-06 11:15**（**协议选型实测（Reality 回滚）**：REALITY 节点在 mihomo 1.19.33 上握手 `Authentication: false`（Xray 26.10 客户端同参数可 204），VLESS Encryption 也未打通；Hysteria2 小请求延迟 96–101ms 但 bulk HTTPS 失败；**生产保留 `VLESS+TLS 8443` 为主、Hy2 备用**，Reality 节点已从 profile/run 回滚。详见 `reports/协议选型实测-20261106.md`）。此前 **2026-11-06 09:55**（**OpenCode 线路优化**：`opencode.ai`（OpenCode Zen/Go API）原走 `🤖 AI → 🛡️ 稳定固定 → 🇸🇬 新加坡-自建TLS`，实测偏慢；2026-11-06 新建 `⚡ OpenCode` select 组（默认 `🌐 全部节点`，当前固定 `[顺畅] 🇯🇵日本-原生01`），并把 `DOMAIN-SUFFIX,opencode.ai` 从 `🤖 AI` 改指该组。交错 4 轮 trace：日本原生中位 **0.63s** / 美国吹雪移联 0.71s / SG 自动 0.83s / 自建 TLS **1.32s**；模型短请求 TTFT 日本原生 **1.2–2.0s** vs 自建 2.2–2.4s（长请求 1.8–2.0s vs 2.4s）。策略组 16→17，规则仍 58；profile 已改 + mihomo 热重载；备份 `/root/bak-opencode-route-20261106-093859/`）。此前 **2026-11-05 23:06**（**290490 子域分流修复**：`vklogo.290490.xyz` / `learn.290490.xyz` 虽属 `*.290490.xyz`，但托管在 Cloudflare，原被 `DOMAIN-SUFFIX,290490.xyz → 🎯 直连` 兜住，直连落 LAX，实测 5–20s / 超时；2026-11-05 新增两条 `DOMAIN,…,🚀 默认代理`（规则 56→58，profile 与 run 同步、mihomo API 热重载未重启），实测 0.6–1.0s；备份 `/root/bak-rule-290490-20261105-230358/`）。此前 **2026-11-03 20:35**（**LuCI 全面检查 + 清理**：① 删除陈旧 DNAT `dsh_ssh`（WAN 2222 → 旧 IPv6）与 `openvpn` 入站放行（1194）；② 关闭明文服务 telnetd(23)/vsftpd(21)/samba(137-445，约 12MB) 与未运行的 miniupnpd，LAN 监听面收敛；③ **发现并修掉外网入口隐患**：mihomo 的域名↔IP 映射缓存会钉住重拨前的 AAAA（Cloudflare 已是新值、上游也新，只有 mihomo 答旧值）⇒ 新增 `/usr/bin/dsh-dns-guard.sh`（cron `*/15`，比对后 reload/restart）并加 sysupgrade keep；④ 无线 5G 实测 **ch36/HE160**（文档原为 ch149/HE80，且与旁挂 AP 同信道）——待你决定是否错开；⑤ 内存可用 86→97MB。回滚 `/root/bak-luci-audit-20261103/`，报告 `reports/路由器LuCI全面检查-20261103.md`）。此前 **2026-11-03 19:55**（**外部审阅收尾**：① zdcn 补 `real-ip` + `rule-set:zdcn → 192.168.31.1`（zdcn 里的国内域名从此拿真实 IP、走内核 `@china_ip` 直通；实测 `vipapi.tradepower.net → 39.99.205.168`）；② 删 `nameserver-policy` 的 `geosite:google-cn`（主 nameserver 本就是阿里/腾讯，留着会抢在 oc-cn-domain 前、拿不到联通本地 CDN；实测 `dl.google.com → 211.95.34.129` 联通）；③ 3 个 provider `health-check.interval` 1800→600；④ **TUN 关闭**（`uci set nikki.mixin.tun_enabled=0`，`ip link show nikki` 为空，省 5–10MB）；⑤ **`♻️ 香港自动` 按用户要求重新引用 `CF优选`**（成员 14→20，tolerance 仍 40，CF 未抢到出口）；⑥ 修 §4.4-8/9 重复与 §4.5 CF 矛盾表述。回滚 `/root/bak-nikki-stage3b-20261103/`，脚本 `tools/patch_profile_review_20261103.py`）。此前 **2026-11-03 18:20**（**代理栈性能优化落地 + 固件事实校正**：① QUIC 兜底弃用 `GEOIP`（fake-IP 下每个 QUIC 连接都会触发一次真实 DNS 解析；而 `GEOIP,no-resolve` 在 fake-IP 下**恒不命中**=全拒）→ 改为 `AND,((NETWORK,UDP),(DST-PORT,443),(NOT,((RULE-SET,oc-cn-domain))),(NOT,((GEOIP,CN,no-resolve))),(NOT,((GEOSITE,apple)))),REJECT`，零解析 + Apple QUIC 放行（实测不再白等 0.13s 回落）；② DNS `respect-rules:false` + 上游全国内直连，**国内域名 policy → 路由器 dnsmasq → 联通 ISP DNS**（debug 实证 `[DNS] resolve www.163.com A from udp://192.168.31.1:53`），NCSI/captive 显式直连；③ **IPv6 代理关闭 + 删除 `fake-ip-range6`**（境外 AAAA→NODATA，国内/dsh 真实 AAAA 保留）防 IPv6 黑洞；④ UDP 保持 **TPROXY**（内核 `nft_tproxy.ko` 实际存在、nft 内 `tproxy to :7892` 正常；TUN 走 gvisor 更费 CPU）；⑤ `♻️ 香港自动` 移出 `CF优选`、`tolerance 100→40`（成员 20→14）；⑥ sniffer 只留"纯 IP 取域名"、`override-destination` 全关；⑦ `ntp` 关闭（sysntpd 在跑且内核 NTP 因 fake-IP6 报错）；⑧ 按 live GeoSite.dat 去重 11 条规则（64→56）。mihomo VmRSS 109.9→79.6MB，core.log 0 error。**同日发现：刷 R26.11.3 后 nginx 包丢失 → DSH 3081 崩溃循环，`sh /usr/bin/dsh-restore.sh` 已恢复（200/0.03s）**。回滚 `/root/bak-nikki-opt-20261103/` + `/root/bak-nikki-stage2-20261103/`，脚本 `tools/patch_profile_20261103.py` + `tools/deploy_nikki_opt_20261103.sh` + `tools/update_agents_20261103.py`，报告 `reports/代理栈-QUIC-DNS-sniffer优化-20261103.md`。此前 **2026-11-03 17:16**（`open-design.ai` 从 `🤖 AI`（SG 自建 TLS）改走 `🚀 默认代理`（香港更快）；规则位置提前到 AI 规则块之前。实测出口链 `amr-link.open-design.ai → [吹雪] 🇭🇰香港•移联02 → ♻️ 香港自动 → 🚀 默认代理`，出口 IP `18.163.89.55` / HK。另确认 `🚀 默认代理` 当前选中 `♻️ 香港自动`（15/20 alive）。回滚 `/root/bak-opendesign-20261103-171246/`，脚本 `tools/fix_opendesign_route.py`。此前 **2026-11-03 10:05**（清理无引用策略组：删除 `📺 YouTube`/`🔍 Google`/`🤖 ChatGPT`/`✈️ Telegram` 四组（rules 段引用均为 0，面板 `/proxies` 已确认消失）；`GEOSITE,telegram` 改走 `🚀 默认代理`。保留 16 个组。回滚 `/root/bak-cleanup-groups-20261103-100241/`，脚本 `tools/cleanup_groups.py`。此前 **2026-11-03 09:50**（AI/YouTube 分流重组：新建 `🤖 AI` 组（select：`🛡️ 稳定固定`/`🚀 默认代理`/DIRECT）；`GEOSITE,youtube` → `🎬 流媒体`；`GEOSITE,google` → `🚀 默认代理`；Google AI 6 条 + `opencode.ai` + `GEOSITE,category-ai-!cn` → `🤖 AI`；新增 `GEOSITE,openai`/`GEOSITE,anthropic` → `🤖 AI`（`opencode.ai`/`openai`/`anthropic` 都不在 `category-ai-!cn` 里，必须显式写）。★ 另修复：`🎬 流媒体` 从 `🚀 默认代理`（实际落到仅 2/10 alive 的 `♻️ 新加坡自动`）**固化为 `♻️ 香港自动`**，Netflix/Disney TLS 失败立即转 302/200。规则 64 条，见 §4.4 / §4.5 与 `reports/AI与YouTube分流重组-20261103.md`。此前 **2026-11-01 08:00**（DSH 手机端外网直连修复+提速：Pocket 端口漂移 3081→3082 导致公网 502/超时、两条 DNAT 抢流量且 Pocket 只监听 IPv4 必失败 ⇒ 删 DNAT、PC 固定 `proxyPort`、watchdog 自动发现端口；nginx 加 **HTTP/2** + `/assets/` 强缓存 + gzip + 上游 keepalive；DDNS 轮询 **5→30 分钟**（重拨/重启由 hotplug 事件驱动）+ 12h 对账；外网 VPS 实测 **HTTP/2 200 / TTFB 0.22–0.31s**，见 §5 / §7-7。此前 **2026-10-30 10:50**：MatchBest 登录事故：`vipapi.tradepower.net`（阿里云杭州）因 fake-IP + `GEOIP,CN,no-resolve` 被误送进香港机场节点、TLS 被断 ⇒ 条目归 GitHub `Bernardxu123/xu` 的 `zdcn.list`（`RULE-SET,zdcn → 🎯 直连`）、profile 不硬编码，固件侧只把 zdcn 的 CDN 换成可 purge 的 `cdn.jsdelivr.net`；已实测登录成功，见 §7-6。此前 **2026-10-29 21:40**（配置审查：`GEOSITE,google-cn` 提前到 `GEOSITE,google` 之前并加 real-ip/CN DNS 直连；乌龟 403 为后台订阅开关默认关闭的预期态、UA 改动已回退；此前删除 `♻️ CF自动` / `🇨🇫 CF节点` 两个独立分组，`CF优选` 并入 `♻️ 香港自动` / `🇭🇰 香港节点` / `🌐 全部节点`；刷入 **QWRT R26.10.29 / 内核 7.3**：★★ **offload 铁律反转——必须设为「无」（`flow_offloading=0` + `hw=0`），软件卸载与硬件卸载都只有 ~600M**；samba/ipv6set 回到镜像（samba 已 disable）；刷机后 **nginx 包 + CF 优选链路**需要恢复（§5 / §4.6）；PC 侧 IPv6 旧前缀要清理。2026-10-28：新增订阅 **吹雪 / 顺畅**、极速注释、**CF 优选流水线上线**；2026-10-27 全面整理 + 文档重写）
> **2026-11-07 15:40 vlook/pc/vklogo 并入 Learn**：`vlook.290490.xyz` 原走 `🚀 默认代理`（1.25–1.53s，偶发 20s 超时），现与 `pc.290490.xyz`、`vklogo.290490.xyz` 一起改指 `📚 Learn`；vlook 实测 0.48–0.65s（偶发 2.18s）。`xx/dsh.290490.xyz` 与 `*.290490.xyz` 兜底仍直连。规则 74 不变、组 18；profile 22,142B/593 行 sha `ad5b5435…`；备份 `/root/bak-learn-vlook-20261107-154140/`。
> **2026-11-07 15:20 Learn 单独分组**：`learn.290490.xyz` 原走 `🚀 默认代理`（`♻️ 新加坡自动`，实测页面 25.8KB TTFB 0.5–2.6s 抖动），新增 `📚 Learn` select 组（`use` 乌龟/吹雪/顺畅/CF优选 + `filter 港|hk|hong|CF`，19 个候选），当前选 `[顺畅] 🇨🇳香港-i-Cable01`，实测 TTFB 中位约 0.55–0.9s；**CF 节点实测 1.6–12.6s，不作默认**。规则 74 不变、组 17→18；profile 22,163B/593 行 sha `04b5620b…`；备份 `/root/bak-learn-20261107-151910/`。
> **2026-11-06 15:35 Play/Gemini 并入 AI 组**：Google Play/Gemini 全部域名（含 `play.googleapis.com`、`play.google.com`、`play-fe.googleapis.com`、`android.clients.google.com`、`clients3.google.com`、`content-push.googleapis.com`）统一指向 `🤖 AI`，以后只切 AI 组即可（`🌐 全部节点`/`🛡️ 稳定固定`/`🚀 默认代理`/DIRECT）；`GEOSITE,google` 仍走 `🌐 全部节点`，只有 Play/Gemini 跟随 AI 组。规则 **68→74**；profile `21,969B/584 行` sha `9474370b…`；备份 `/root/bak-ai-google-20261106-153511/`。
> **2026-11-06 15:00 Google 规则收敛**：删除 gvt1/2/3、dl.google.com 的旧 `🚀 默认代理` 重复规则；Google Play/Gemini 服务域名统一走 `🌐 全部节点`（当前日本原生，Gemini 支持地区），并补 `dl.l.google.com`/`tools.google.com`/`pki.goog` fake-ip+代理；`GEOSITE,google` 同步改 `🌐 全部节点`；`🤖 AI` 组增加/选中 `🌐 全部节点`。规则 **68 条**；profile `21,477B/572 行` sha `b7a31dc8…`。实测 Play/Gemini 域名 DNS 均 fake-IP、TCP 走日本原生；UDP/443 仍被通用 QUIC REJECT（日志已抓到 `xn--...` 被拒），下一步再做 Play 域名 UDP 例外。备份 `/root/bak-google-clean-20261106-145247/`。
> **2026-11-06 14:35 Google 服务域名修复**：`clientservices.googleapis.com` / `services.googleapis.cn` 实测解析到 `211.95.34.129/139`（属 `@china_ip` 的 `211.80.0.0/12`），被内核 `nft` 的 `ip daddr @china_ip return` 抢先直连，mihomo 规则层根本看不到；已加 `fake-ip` 前置覆盖 + 显式 `🚀 默认代理` 规则（rules **62→64**），实测两域名 DNS 变 `198.18.x`、curl 走代理。`googleapis.cn` 本身 NXDOMAIN 无 A，未加。备份 `/root/bak-google-20261106-143437/`。
> **2026-11-06 11:10 Google Play 下载修复**：`gvt1/gvt2/gvt3.com` + `dl.google.com` 原被 `GEOSITE,google-cn` 的 `real-ip` 抓成联通 IPv6 直连，Play 商店「能看到软件但下载/更新失败」；新增 4 条 `DOMAIN-SUFFIX,...,🚀 默认代理`（排在 `GEOSITE,google-cn` 前）+ 4 条 `fake-ip-filter ... fake-ip` 覆盖，规则 **58→62**；实测 `dl.google.com` 返回 fake-IP 198.18.x、`repository2-1.xml` 200、8MB 测试文件 0.97s（约 66Mbps），`redirector.gvt1.com` 已走代理。备份 `/root/bak-play-20261106-110106/`。
> **2026-11-06 11:15 协议实测**：VPS Reality 入站（20894）用 mihomo 1.19.33 客户端握手 `REALITY Authentication: false`，同参数 Xray 26.10 客户端可 204；已排除 flow/shortId/servername/fingerprint/xudp 等变量。Hysteria2 小请求延迟 96–101ms，但 50MB/5MB `speed.cloudflare.com` TLS 握手失败；VLESS+TLS 8443 下载 10.1–12.1 MB/s（约 81–97 Mbps）、稳定。结论：`🛡️ 稳定固定 → 🇸🇬 新加坡-自建TLS` 保持，Hy2 备用；Reality 节点已回滚，3x-ui `router-vision` 客户端保留未用。备份 `/root/bak-proto-20261106-102524/`、`/root/bak-proto-router-20261106-103242/`、`/root/bak-proto-cleanup-*`。
> 本文件是**唯一事实源**。凭据见 `凭据.md`；历史过程报告见 `reports/`；固件与设备备份见 `01-`/`02-` 目录。
> ⚠️ 文中的结论均为实测所得，**标 ★ 的是踩过坑的铁律，别绕开**。

---

## 0. 使用约定（动手前先读）

1. **先读再改**：改任何配置前，确认它属于哪一层（nft 内核旁路 / mihomo 规则 / dnsmasq / fw4 offload），层次搞错会得出错误结论。
2. **改完必须验**：代理栈改动后至少验 4 项 —— ① `nikki status` = running ② 核心日志无 error ③ 国内域名真实 IP + 国外域名 fake-IP ④ 内外网各一个站点能打开。
3. **备份先行**：路由侧备份到 `/root/bak-<主题>-<日期>/`；PC 侧本仓库有 git。
4. **克制**：一次只改一个变量，改完留验证数据；不要"顺手"动无关项（历史上多次因为顺手改 TUN/MTU/IRQ 引入新问题）。
5. **判据优先**：不确定时用数据说话（见 §7 判据表），不要按域名或直觉猜归属。

---

## 1. 线路与拓扑

| 项 | 现状 |
|---|---|
| 运营商 | 中国联通，**1000M** 下行；WAN 走 **CGNAT**（`100.80.x.x/10`，会随重拨变） |
| PON | 10G-EPON 非对称，模式 `epon-10g-1g`，OAM **CTC** + LOID；VLAN 995 拨号，TR069 走 VLAN 28 |
| 拨号 | **PPPoE over `pon0.995`** → 逻辑接口 `pppoe-wan`，协商 MTU **1492** |
| IPv6 | `pppoe-wan` 拿全局 `2408:820c:...::/64`；LAN 分到 **/60** 前缀；另有 ULA `fdae:8777:3859::/60` |
| 光路质量 | `rx_crc_errors 0` / `uncorrected_codewords 0` / `fec_error_seconds 0` / `mac_errors 0`（2026-10-27 复核） |
| 入站端口 | 运营商封 80/443，对外服务走 3081 等高位端口 |

```
PON(光纤) ──pon0.995──> [烽火 HG5585F = 光猫兼主路由 QWRT 192.168.31.1] ──br-lan──┬─ 小米 BE6500 Pro AP(.138, 有线回程)
                          └── pppoe-wan (CGNAT + 公网 IPv6)                        ├─ PC 有线 .218 (1GbE)
                                                                                    └─ 手机/平板/IoT
```

---

## 2. 设备与地址

**关键设备**（完整 23 条静态租约见 `reports/静态IP与设备绑定-20261023.md`；`/etc/hosts` 里有静态名，`*.lan` 可解析）：

| 设备 | IP | 说明 |
|---|---|---|
| 主路由 烽火 HG5585F | `192.168.31.1` | hostname `ct-hg5585f`，MAC `d0:69:ff:16:32:80` |
| 小米 AP BE6500 Pro | `192.168.31.138` | IPQ5332，**自配静态（非 DHCP）**，旁挂 AP 有线回程，SSID `bernard` / `bernard_5G` |
| 主力 PC | `192.168.31.218` | 有线 Realtek 1GbE（`pc_eth`）；WiFi 租约 `pc_wlan` = `.222` |
| 华为平板 DMG-W00 | `192.168.31.122` | 随机 MAC，租约会漂 |
| 小米 14 Pro | `192.168.31.221` | |
| 华为 P30 Pro | `192.168.31.155` | 连接数最多 |
| OPPO Reno6 | `192.168.31.198` | |
| 石头扫地机 | `192.168.31.153` | |
| IoT | `.101/.182` 小爱音箱、`.220` 摄像头、`.239` 微波炉、`.102` 电饭煲、`.164/.240` 海尔空调 | |
| Vidda S70 电视 | `192.168.31.208` | 常离线 |

**无线**：主路由 2.4G `ch11/HE20`（2026-10-29 实测 UCI，旧文档写 ch6）、5G `ch149/HE80`（**country 必须 CN**，否则 ch149 是 NO-IR）；AP 2.4G `ch1/HT40`、5G `ch36/160`。手机/平板为随机 MAC，关掉"随机 MAC"才能让租约稳定。

---

## 3. 主路由（HG5585F / QWRT）

### 3.1 版本与硬件
- 固件 **QWRT R26.11.10**（**2026-11-10 刷入**；底层 OpenWrt **25.12.3**，`DISTRIB_REVISION='R26.11.10'`），内核 **`5.4.302`**（2026-11-03～11-09 曾用 R26.11.3 / 内核 7.3.1，11-10 升回 5.4.302 线），`aarch64`
- ★ **每次升级/重刷都会把这些「非 keep 的 rootfs 文件」换回厂商版**：`/usr/share/ucode/fw4.uc`（掉 offload 补丁，靠 §3.3 的开机钩子自动重打）、`/usr/sbin/nginx`（掉 nginx-ssl 包，靠 `sh /usr/bin/dsh-restore.sh`）、`/www/luci-static/resources/view/nikki/app.js`
- SoC **Airoha AN7581**，4×Cortex-A53，RAM **412604 kB（≈403MB）**，**无 swap**（overlay 是 ubifs，不支持 swapfile）
- 已有模块：`nf_flow_table{,_hw,_inet}`、`an7581_bsp_ppe`（依赖 `br_netfilter` + `nf_flow_table_inet`，并替换 `nf_flow_offload_{ip,inet}_hook`）、`nft_tproxy`、`xt_TPROXY`
- 其它版本事实（**R26.11.3，2026-11-03 实测**）：`nikki 2026.10.10-1` / `luci-app-nikki 1.26.2-r1` / `luci-mod-network 2026.10.25-2` / `mihomo 1.19.33-1`（镜像内版本，以 `mihomo -v` 为准）；`samba36-server 4.25.0-4` / `luci-app-ipv6set 1-r6` 仍在镜像（samba 已 `disable`）；`nft_tproxy.ko` 存在于 `/lib/modules/7.3.1/`

### 3.2 关键 UCI

```sh
# 网络
network.wan.proto=pppoe ; network.wan.mtu=1500        # ★ 必须 1500；pppd 会自己协商成 1492
                                                       #   切勿手动填 1492（会二次扣减成 1484）
network.wan.mru=1500
network.@device[?wan].mtu=1500                         # pon0 侧维持 1500

# ★★ 防火墙 offload（600M 事故的根因，见 §7-1）
firewall.@defaults[0].flow_offloading=0                # ★★ 内核 7.3 起必须「无」；=1 只有 ~600M
firewall.@defaults[0].flow_offloading_hw=0             # 硬件卸载：同样必须 0
```

### 3.3 offload 行为（2026-10-29 实测，内核 7.3）
```
flow_offloading=0 + hw=0（「无」） → 没有 flowtable，conntrack 里 0 条 [OFFLOAD] → 满速
flow_offloading=1 + hw=0（软件）   → 有 flowtable（7.3 上 devices 会全量列出 br-lan/lan1-4/pon0/pon0.995/pppoe-wan/ra0/rai0）→ ~600M
flow_offloading=1 + hw=1（硬件）   → flowtable 变物理口 + flags offload → ~600M
```
判据（**2026-11-10 起以 R26.11.10 / 内核 5.4.302 为准**）：软件卸载下 `nft list table inet fw4 | sed -n '/flowtable ft/,/}/p'` 必须是 `devices = { "br-lan", "pon0.995", "pppoe-wan" }` 且**没有** `flags offload`；硬件卸载则是 7 个物理口 + `flags offload`。「无」= 没有 flowtable、conntrack 里 0 条 `[OFFLOAD]`。

> **历史（5.4.302 / R26.10.25-26）**：软件 914M、硬件 640M、全关 845M —— 与 7.3 结论**相反**，别套用。
> 原因（推断；证据：`an7581_bsp_ppe.ko` 依赖 `nf_flow_table,br_netfilter,nf_flow_table_inet`、替换了 `nf_flow_offload_{ip,inet}_hook`，且模块内无任何 pppoe 符号）：7.3 上 PPE 会接管 flowtable 条目但不会补 PPPoE 头 ⇒ 只要存在 flowtable，PPPoE 流就被拖进半残快路径。
> ★★ **2026-11-06 重测（R26.11.6 / 内核 5.4.302，speedtest.cn 上海联通）—— 结论改为「软件卸载」**：
> | 档位 | 下行 | 说明 |
> |---|---|---|
> | 无卸载 `0/0` | 1,026 Mbps | 满速 |
> | 硬件卸载 `1/1` | 632 Mbps | PPE 有绑定（PPE0:1/PPE1:40）但带宽腰斩，**永久弃用** |
> | **软件卸载 `1/0`（修复后）** | **1,022 Mbps** | ✅ 满速 + `[OFFLOAD]` 条目正常增长 |
>
> ★ **软件卸载此前"失效"的真因不是不支持，而是 flowtable 设备数超限**：厂商内核/PPE **每张 flowtable 最多 7 个设备**（7 个成功、8 个报 `File too large`）；fw4 在软件档会列 10 个（`br-lan, lan1-4, pon0, pon0.995, pppoe-wan, ra0, rai0`）⇒ `nft` 返回 EFBIG，`firewall restart` 中止并保留旧规则集（界面显示已切换，实际没生效）。硬件档只列 7 个物理口，恰好不超限，所以"硬件能开、软件开不了"。
> **修复**：`/usr/share/ucode/fw4.uc` 的 `resolve_offload_devices()` 增加裁剪 —— 设备数 >7 时丢掉"上层已覆盖的下层设备"（桥端口、VLAN 父口），得到 `devices = { br-lan, pon0.995, pppoe-wan }`。修复后 `firewall restart` exit 0。
> **持久化（2026-11-10 改版，★ 旧办法已被证明无效）**：`/etc/dsh-fw4-offload-fix.block` + `/usr/bin/dsh-fw4-offload-fix.sh`（幂等，已打则退出；`--no-reload` 供开机用）都在 `sysupgrade.conf` keep 里，**由 `/etc/init.d/dsh-fw4-offload-fix`（`START=18`，早于 firewall `S19`，`/etc/rc.d/S18…` 已 enable）在每次开机时重打**——因为每次升级都会换掉 rootfs 里的 `fw4.uc`。★ 旧 cron `@reboot sleep 20; /usr/bin/dsh-fw4-offload-fix.sh` **从未生效**（busybox crond 1.35 不支持 `@reboot`，2026-11-10 已删）。脚本带兜底：锚点失效或生成出来的 flowtable 仍 >7 个设备时，自动把 `flow_offloading` 关成「无」并记 `user.err`，保证 fw4 一定能加载。厂商原文件每次打补丁前备份到 `/root/bak-fw4.uc.<ts>`；2026-11-10 升级前原件另存 `/root/bak-offload-20261110/fw4.uc.orig`。
> 判据改为：软件卸载下 `nft list table inet fw4 | grep -A3 flowtable` 应有 `devices = { "br-lan", "pon0.995", "pppoe-wan" }`，且下载中 `[OFFLOAD]` 计数 >0。

### 3.4 sysctl / 队列（已在目标状态，勿动）
`tcp_congestion_control=bbr`、`default_qdisc=fq_codel`、`tcp_mtu_probing=1`、`netdev_max_backlog=4096`、`rmem_max=wmem_max=1048576`。

### 3.5 持久化与定时任务
`/etc/sysupgrade.conf` 保留：`/etc/nikki/`、`/etc/dsh-nginx/`、`/etc/init.d/dsh-nginx`、`/usr/bin/dsh-watchdog.sh`、**`/usr/bin/dsh-dns-guard.sh`**、`/etc/acme.sh/`、`/etc/dsh-nginx/cert/`、`/etc/crontabs/root`、`/etc/sysctl.d/`、`/etc/cf-dns.token`、`/etc/dsh-ddns-last`、`/etc/dsh-cf-{zone,record}.id`、`/etc/init.d/pon-macclone`、`/usr/lib/ddns/update_cloudflare_dsh.sh`、`/etc/cf/`、`/usr/local/bin/cf-refresh.sh`（后两项 2026-10-29 才补进 keep；之前刷机会把 CF 链路整条丢掉）；**2026-11-10 再补 `/usr/bin/dsh-fw4-offload-fix.sh`、`/etc/dsh-fw4-offload-fix.block`、`/etc/init.d/dsh-fw4-offload-fix`**（`/etc/init.d` 本身在 overlay 里也会被保留，keep 只是双保险）。

cron 现 7 条（2026-11-10 删掉无效的 `@reboot sleep 20; …dsh-fw4-offload-fix.sh`——busybox crond 1.35 不支持 `@reboot`，offload 补丁改由 `S18dsh-fw4-offload-fix` 开机钩子执行）：acme 续期（`17 3 * * *`）、nikki 日志清理（`*/5`）、nginx `check_ssl`（`3 3 12 12 *`）、**`*/5 * * * * /usr/bin/dsh-watchdog.sh`（DSH 入口/DDNS 看门狗；2026-11-01 从 `*/2` 降到 `*/5`，轻量化）**、**`17 4 * * * /usr/local/bin/cf-refresh.sh`（CF 优选刷新，40h 门控 → 实际 40–56h 一轮，见 §4.6）**、`0 2 * * *`（清 `msd_lite` 日志）、**`*/15 * * * * /usr/bin/dsh-dns-guard.sh`（mihomo DNS 映射守护，见 §5）**。

> ⚠️ `/etc/config/nikki` 与 profile 都在 `/etc/nikki/` 下，升级保留；但 **`/www/luci-static/resources/view/nikki/app.js` 不在 keep 里**，重刷固件后 LuCI 页面会回到原版（见 §7-2）。

---

## 4. 代理栈：nikki + mihomo

### 4.1 组件与端口

| 项 | 值 |
|---|---|
| nikki | `2026.10.10-1`，`luci-app-nikki 1.26.2-r1` |
| mihomo | `v1.19.33` linux/arm64（go1.27.3），`/usr/bin/mihomo → /usr/libexec/mihomo` |
| 数据面 | **TCP = redirect(7891)**、**UDP = tproxy(7892)**（`nikki.proxy.udp_mode='tproxy'`，nft 内 2 条 `tproxy to :7892`）；**IPv6 代理已关**（`ipv6_proxy=0`，只代理 IPv4）；**TUN 已关闭**（`nikki.mixin.tun_enabled=0`，`ip link show nikki` 为空；此前虽不在主路径但 gvisor 栈常驻，关掉省 5–10MB；别为"内核无 nft_tproxy"改 TUN——该前提是错的） |
| DNS | mihomo 监听 `[::]:1053`；LAN 的 `:53` 被 nft **劫持到 1053** |
| 面板 | `[::]:9090`，`allow_lan=1`，secret 见 `凭据.md`（**6 位，偏弱**） |
| 配置 | uci `nikki.config.profile='file:openclash-20261022.yaml'` |
| | 源文件 `/etc/nikki/profiles/openclash-20261022.yaml`（**26,143B / 650 行，sha256 `c4b8f318…`**；2026-11-10 20:05 去重+注释对齐+dsh policy 后，改前 25,176B/644 行/`1679f563…`）→ 运行时 `/etc/nikki/run/config.yaml`（**规则 74 条 / 策略组 22 个**） |
| 订阅源 | `proxy-providers` **订阅源生效 3 个**：`乌龟`、`吹雪`、`顺畅`（后两个 2026-10-28 新增）；另有 **file provider `CF优选`**（`/etc/nikki/run/providers/cf-optimized.yaml`，§4.6）；**`乌龟` 需在网站后台开启「订阅」开关才会订阅（默认关），403 属预期；它保留缓存节点、节点故障时再更新，不要加 UA header（2026-10-29 已回退）**；`极速` **已注释**（2026-10-28 流量用尽，provider 块和 8 处 `use:` 条目都带 `#`，**恢复时两处一起去 `#`**，只去一处会导致配置校验失败）→ 缓存 `/etc/nikki/run/providers/proxy/{wugui,chuixue,shunchang}.yaml`（`jisu.yaml` 旧缓存仍留在盘上但不加载），节点自动加前缀 `[名] `，`interval: 86400` 由 mihomo 自己刷新（**没有 cron 依赖**） |

### 4.2 内核级「绕过大陆」（最省性能的一层）
- `nikki.proxy.bypass_china_mainland_ip=1`、`nikki.proxy.bypass_china_mainland_ip6`
- nft 表 `inet nikki` 的 `dstnat` / `mangle_prerouting_lan` / `nat_output` 里，`ip daddr @china_ip counter return` **排在所有 redirect 之前** ⇒ 命中即回内核直连，**根本不进 mihomo**
- `@china_ip` = **7362** 段、`@china_ip6` = **1655** 段，来自 `/etc/nikki/nftables/geoip{6}_cn.nft`（**包自带静态文件，无自动更新任务**）
- 判 CN 归属必须查集合，不能看域名：
  ```sh
  nft get element inet nikki china_ip '{ 140.207.247.169 }'
  ```

### 4.3 DNS 架构（三层，别搞混；2026-11-03 重写）

| 层 | 行为 |
|---|---|
| LAN 客户端查 `:53` | 被 nft `lan_dns_hijack` 直接 redirect 到 `mihomo:1053`（**dnsmasq 被绕过**） |
| mihomo DNS | fake-ip `198.18.0.1/16`（**已无 `fake-ip-range6`**，见 §7「其他常备事实」）；`fake-ip-filter` 用 rule 模式：`DOMAIN,dsh.290490.xyz`→real-ip、`RULE-SET,oc-cn-domain`/`RULE-SET,zdcn`/`GEOSITE,private`/`GEOSITE,google-cn`→real-ip（**但 `gvt1/gvt2/gvt3/dl.google.com` 与 `clientservices.googleapis.com`/`services.googleapis.cn` 2026-11-06 起用 `fake-ip` 前置覆盖，见 §7-9**）、`*.lan/*.local`、NCSI/captive/NTP 域名→real-ip、`MATCH,fake-ip` |
| 上游（2026-11-03 起） | **`respect-rules: false`**（DNS 不跑规则表、不经代理）；`nameserver` = `223.5.5.5 / 119.29.29.29`；**`nameserver-policy`**：`+.lan` / `geosite:private` / `rule-set:oc-cn-domain` / **`rule-set:zdcn`** → **`192.168.31.1`（路由器 dnsmasq → 联通 ISP DNS 210.22.70.225/.3，CDN 就近）**；**2026-11-03 晚已删除 `geosite:google-cn` 的 policy**（主 nameserver 本来就是阿里/腾讯，留着只会抢在 oc-cn-domain 之前、拿不到联通本地 CDN）；**不写 `direct-nameserver`**（理由见 §7「其他常备事实」）；**2026-11-10 20:05 新增 `"dsh.290490.xyz" → 223.5.5.5 / 119.29.29.29`**（DDNS 记录只有 AAAA，ISP 多个缓存实例分裂会让 guard 反复重启 nikki，见 §5）；境外域名一律 fake-IP，不落地解析 |

判据（2026-11-03 实测）：PC 查 `www.baidu.com / qq / taobao / bilibili` → 真实国内 IP；`www.google.com / youtube / chatgpt` → `198.18.x`；`tablet.lan` → `192.168.31.122`；debug 日志 `[DNS] resolve www.163.com A from udp://192.168.31.1:53` **直接证明国内域名走 dnsmasq**；zdcn 闭环后 `vipapi.tradepower.net → 39.99.205.168`（真实 CN IP，不再是 `198.18.x`）；`dl.google.com` 2026-11-06 起改为 fake-IP `198.18.x`（Play 下载修复，见 §7-9）。

### 4.4 规则表（**74 条**，自上而下首个命中；2026-11-03 去重 + QUIC 重写，2026-11-05 +2 条 290490 子域，2026-11-10 Google 独立成组，2026-11-10 20:05 删 2 条被 290490 后缀同目标覆盖的死规则）
顺序要点（**改规则前必须确认前面没有更早规则吃掉流量**）：
1. `GEOSITE,private` + 一堆保留网段 `IP-CIDR` → 🎯 直连
2. STUN/游戏 UDP（3478/19302/7844）、NTP(123) → 直连
3. `AND,((NETWORK,UDP),(DST-PORT,443),(NOT,((RULE-SET,oc-cn-domain))),(NOT,((GEOIP,CN,no-resolve))),(NOT,((GEOSITE,apple)))),REJECT`
   → **境外 QUIC 零解析拦截**（`domainStrategy` 只看 `RuleHost`，不触发 DNS）：国内域名放行 HTTP/3、🍎 Apple 放行（该组默认 DIRECT）、其余 QUIC 立即 REJECT 让浏览器秒回落 TCP
   ★ 旧写法 `(NOT,(GEOIP,CN))` 会在**每个** QUIC 连接上触发一次真实 DNS 解析；而加 `no-resolve` 后 fake-IP 下**恒不命中**（= 全拒）——源码见 §7-6
   → 紧随其后 3 条 `DOMAIN-SUFFIX,msftconnecttest.com / msftncsi.com / captive.apple.com → 🎯 直连`：连通性检测不走代理，避免"Wi-Fi 感叹号"（2026-11-03 新增）
   ★ **为什么不能取消 QUIC 拦截（2026-11-03 晚复核）**：原始理由（OpenClash/daed 时代**根本没有 UDP 代理**）已消失——现在 UDP tproxy + SOCKS5 UDP 中继实测可用；但**节点 UDP 质量参差**：`[CF] HK-1-01` **0/3 不通**（Worker VLESS-WS 只支持 UDP:53）、`[顺畅] 🇨🇳香港原生htk高速` 3/3 但中位 **2441ms**、`[乌龟] 🇭🇰 HongKong-AnyTls` **185ms**、`[吹雪] 🇭🇰香港•移联01` **319ms**。而 url-test **只测 TCP**、无法避开 UDP 差的节点（当时 `♻️ 香港自动` 恰好选中的就是 2.4s 的顺畅 htk）⇒ 直接放开会重现"某设备走 QUIC 卡住不回落"。工具：`tools/socks5_udp_probe.py`、`tools/quic_udp_matrix.py`。若确实要 HTTP/3，正解是**新建 `⚡ UDP 转发` select 组（只放 UDP 实测 OK 的节点，排除 CF 与顺畅 htk），把 QUIC 规则的 REJECT 改成指向该组**，而不是简单删掉 REJECT。
4. 自有服务：**`vlook/pc/vklogo/learn.290490.xyz` → `📚 Learn`**（2026-11-07：Learn 组 19 个 HK/CF 候选，当前 `[顺畅] 🇨🇳香港-i-Cable01`；learn TTFB 0.55–0.9s、vlook 0.48–0.65s；CF 实测 1.6–12.6s 不作默认）；`xx/dsh.290490.xyz` 与其余 `*.290490.xyz` → 直连
   + **`tradepower.net`（MatchBest 后台 API，阿里云杭州 39.99.205.168）走 `RULE-SET,zdcn` 直连**（2026-10-30；条目写在 GitHub `Bernardxu123/xu` 的 `zdcn.list` 里，profile 不硬编码，原因见 §7-6）
   + **Google Play 下载域名（2026-11-06）**：`gvt1.com`/`gvt2.com`/`gvt3.com`/`dl.google.com` → `🚀 默认代理`，必须排在 `GEOSITE,google-cn` 之前；否则这些域名被 google-cn 判成直连，Play 能看不能下。DNS 侧同步在 `fake-ip-filter` 顶部加 `fake-ip` 覆盖（见 §4.3 / §7-9）。
   + **Google Play/Gemini 服务域名（2026-11-06 15:35 并入 AI 组）**：`services.googleapis.cn`、`xn--...com`、`dl.google.com`、`dl.l.google.com`、`clientservices.googleapis.com`、`gvt1/2/3.com`、`tools.google.com`、`pki.goog`，再加 `play.googleapis.com`、`play.google.com`、`play-fe.googleapis.com`、`android.clients.google.com`、`clients3.google.com`、`content-push.googleapis.com`，统一 → **`🔐 Google`**（2026-11-10 从 🤖 AI 移出、单独成组；见 §4.5）；全部加 `fake-ip` 前置覆盖；必须排在 `googleapis.cn` 直连、`RULE-SET,zdgw`、`GEOSITE,google-cn` 之前。`GEOSITE,google`、`GEOSITE,google-gemini` 也一并走 `🔐 Google`；旧的 gvt1/2/3/dl `🚀 默认代理` 重复规则已删除。
5. `googleapis.cn` → 直连；`speedtest.cn` → ✈️ Speedtest(=DIRECT)
6. `RULE-SET,zdcn` → 直连；`RULE-SET,zdgw` → 默认代理
7. Steam 内容/Cdn 直连，`GEOSITE,steam` → 默认代理
8. **AI 组（2026-11-03 重组 + 去重）**：只保留 `GEOSITE,category-ai-!cn` → 🤖 AI（**`opencode.ai` 已于 2026-11-06 移出本组，改走 `⚡ OpenCode`**；**2026-11-10 起 `alkalimakersuite-pa.googleapis.com` / `.clients6` 移入 `🔐 Google`，本组现在只管非 Google AI（ChatGPT/Claude 等）**）
9. `GEOSITE,youtube` → **🎬 流媒体**（原 📺 YouTube）；**`open-design.ai` → 🎨 OpenDesign（2026-11-07 独立成组；默认 `♻️ 新加坡自动`，脚本可切 `🎨 OpenDesign 池`；位置提前到 AI 规则块之前）**（🤖 AI 的 3 条见第 8 条，此处不重复）
   ★ **去重结论（实测 live `GeoSite.dat` 10-26 快照，1508 tag）**：`GEOSITE,apple-cn`（164/164 ⊆ apple）、`GEOSITE,google-gemini`（39/39 ⊆ category-ai-!cn）、`GEOSITE,openai`（20/20）/`GEOSITE,anthropic`（8/8）⊆ category-ai-!cn、`aistudio/makersuite/alkalimakersuite-pa.clients6/generativelanguage` 与 3 条 github 子域 **均已删除**（被更早的同目标规则完整覆盖）——**旧文档"openai/anthropic 不在 category-ai-!cn"是错的**（v2fly 源即 `include:openai`/`include:anthropic`）
   ★ **`GEOSITE,google-cn` 必须保留**（目标不同：直连 vs 代理，且必须排在 `GEOSITE,google` 之前）
   ★ **`open-design.ai` 单独走 `🎨 OpenDesign`**：OpenDesign 后端（`amr-link.open-design.ai` / `amr-api.open-design.ai`）2026-11-07 实测 TTFB 0.59–0.70s、colo SIN；默认钉 `♻️ 新加坡自动`（不再跟全局 `🚀 默认代理` 漂移）；若退化，脚本按 30%/150ms 门槛切池。
10. 流媒体（netflix/disney/spotify/tiktok）、GitHub、Telegram、Twitter、Google（`GEOSITE,google` → **🔐 Google**，2026-11-10 起；原 🔍 Google）、**`GEOSITE,google-cn → 🎯 直连`（必须排在 `GEOSITE,google` 之前；2026-10-29 修正，否则 112 个 google-cn 域名全被 GOOGLE 规则吃掉）**、Apple、OneDrive、Microsoft、Oracle、Ookla
11. `RULE-SET,oc-cn-domain → 直连` → `GEOIP,CN,no-resolve → 直连`（★ fake-IP 下 DstIP 已被清空，该条**恒不命中**，只作纯 IP 长尾兜底）→ `MATCH → 🐟 漏网之鱼`

### 4.5 分组与出口
`🚀 默认代理`（**2026-11-07 实测选中 `♻️ 新加坡自动`**，now=`[吹雪] 🇸🇬新加坡•移联01`；11-03 曾切香港自动）、`🤖 AI`（2026-11-03 新建，select：`🌐 全部节点`/`🛡️ 稳定固定`/`🚀 默认代理`/DIRECT，**2026-11-10 当前 `🚀 默认代理`，只管非 Google AI（ChatGPT/Claude 等）；Play/Gemini 已移入 `🔐 Google`**）、`🔐 Google`（2026-11-10 新建，select：`🇸🇬 新加坡节点`/`🚀 默认代理`/`🌐 全部节点`/DIRECT；**当前 `🇸🇬 新加坡节点 → [乌龟] 🇸🇬 Singapore-AnyTls`**，Google 全站（Gemini/AI Studio/Play/accounts/www/gstatic）同组同 IP，避免跨区验证）、`⚡ OpenCode`（2026-11-07 重构，select：`🛡️ 稳定固定`/`⚡ OpenCode 池`/`🚀 默认代理`/`🌐 全部节点`/DIRECT；**当前 `🚀 默认代理`**，专供 `opencode.ai` Zen/Go API）、`⚡ OpenCode 池`（select，use 3 家 + 亚洲 filter，46 个候选，脚本选节点）、`🎨 OpenDesign`（2026-11-07 新建，select：`♻️ 新加坡自动`/`🎨 OpenDesign 池`/`🚀 默认代理`/`🌐 全部节点`/`♻️ 香港自动`/`🛡️ 稳定固定`/DIRECT；**默认 `♻️ 新加坡自动`**）、`🎨 OpenDesign 池`（同 filter，46 个候选）、`🛡️ 稳定固定`（→ `🇸🇬 新加坡-自建TLS`；**2026-11-10 20:05 已选回 TLS**（delay 187ms），Reality 回滚、Hy2 只作备用——2026-11-06 实测 Hy2 小请求可用但 bulk HTTPS 失败）、`♻️ 香港自动`、`🎯 直连`、`🐟 漏网之鱼`、`✈️ Speedtest`(DIRECT)、`🎬 流媒体`（**2026-11-03 固化为 `🚀 默认代理`**）、`📦 GitHub`、`🪟 微软`、`🍎 Apple`、`🏢 甲骨文 Oracle`。

> **2026-11-03 10:05 清理**：已删除 4 个「规则引用为 0」的策略组 —— `📺 YouTube`、`🔍 Google`、`🤖 ChatGPT`、`✈️ Telegram`（用户要求面板干净 + Telegram 走默认代理）。
> `GEOSITE,telegram` 规则已改为 `🚀 默认代理`。删除前逐个校验 `rules` 段引用数 = 0，删除后 `mihomo -t` 通过、面板 `/proxies` 清单已无这四个组。
> **保留**：`🚀 默认代理`/`🤖 AI`/`🔐 Google`/`⚡ OpenCode`/`⚡ OpenCode 池`/`🎨 OpenDesign`/`🎨 OpenDesign 池`/`📚 Learn`/`🛡️ 稳定固定`/`♻️ 香港自动`/`♻️ 新加坡自动`/`🇭🇰 香港节点`/`🇸🇬 新加坡节点`/`🌐 全部节点`/`🎬 流媒体`/`🎯 直连`/`🐟 漏网之鱼`/`✈️ Speedtest`/`📦 GitHub`/`🪟 微软`/`🍎 Apple`/`🏢 甲骨文 Oracle`（共 22 个）。
> 回滚：`/root/bak-cleanup-groups-20261103-100241/`；脚本 `tools/cleanup_groups.py`（幂等，支持 `--dry`）。

节点来源：8 个组用 `use:` 引用**当前生效的 3 个 provider**（`乌龟`/`吹雪`/`顺畅`；`极速` 已注释），其中 `♻️ 香港自动` / `🇭🇰 香港节点` / `🌐 全部节点` **都引用 `CF优选`**（2026-10-29 起原 `♻️ CF自动` / `🇨🇫 CF节点` 两个独立分组已删除，CF 节点只作备用并入）——`♻️ 香港自动`/`♻️ 新加坡自动` 是 url-test（gstatic 测速，组 `interval: 600` / **容差 40**）；**2026-11-03 18:20 曾把 CF 移出 `♻️ 香港自动`（成员 20→14），19:55 按用户要求加回（14→20，实测 6 个 CF 成员）**，tolerance 仍保持 40（CF 实测 8Mbps / 189ms vs 机场 50–100ms，容差 40 下 CF 不会抢出口；旧 tolerance 100 才是"粘住不切"的根因）；★ 对 `use:` 型组，组的 `interval`/`lazy` **不生效**，节点测速周期由 provider 的 **`health-check.interval=600`（2026-11-03 晚从 1800 改）** 决定，`🇭🇰 香港节点`/`🇸🇬 新加坡节点`/`🌐 全部节点` 是 select；组内节点名形如 `[吹雪] 🇭🇰香港•移联01`，靠 filter `港|hk|hong ?kong` / `新加坡|狮|singapore|sg-?[0-9]` 归组，`exclude-filter` 剔除「剩余流量/套餐到期」这类信息节点。**`♻️ 香港自动` 额外排除 `家宽`**（2026-10-28：顺畅家宽节点延迟很低 37–56ms 但实测吞吐偏慢）；注意 exclude-filter 是**逐组**字段，其余组仍能看到家宽节点。**新增机场只动 provider + 8 处 `use:`（含两个 API 池），不要建平行新组**（2026-10-28 吹雪/顺畅即按此办理）。

> ★ **`opencode.ai` 线路实测（2026-11-06，交错 4 轮 trace）**：`[顺畅] 🇯🇵日本-原生01` 中位 **0.63s**、`[吹雪] 🇺🇸美国•移联01` 0.71s、`♻️ 新加坡自动` 0.83s、`[吹雪] 🇭🇰香港•移联01` 0.87s、`🇸🇬 新加坡-自建TLS` **1.32s**。模型短请求（16 tok）TTFT：日本原生 1.2–2.0s vs 自建 2.2–2.4s；长请求（100 tok）1.8–2.0s vs 2.4s。上游（OpenCode/DeepSeek）本身抖动可达数秒，路由差异主要体现在边缘 RTT。2026-11-06 实测 `🚀 默认代理` = `♻️ 新加坡自动`（用户面板手动切换，未改）。
> ★ **2026-11-07 API 线路实测（10 次采样，经路由器透明代理）**：`opencode.ai/zen/go/v1/models` 从 `🛡️ 稳定固定` 的 TLS 0.80s / TTFB 1.31s 降到 `🚀 默认代理` 的 TLS 0.26s / TTFB 0.57s（10/10 200，colo SIN，出口 3.1.90.74）；`amr-link.open-design.ai/v1/models` 保持 `♻️ 新加坡自动` TTFB 0.59–0.70s（401，10/10）。**吞吐口径纠正**：curl `speed_download` 是 bytes/s，旧文档当成 kbps/Mbps 放大了 1000 倍；同源 2MB 视频 `opencode.ai/files/site/2026-11/.../desktop.mp4` 实测 12–22 Mbps（`🚀 默认代理`），首页 193–262KB 小包只有 3–4 Mbps（慢启动限制，不代表链路带宽）。

### 4.6 CF 订阅优选流水线（2026-10-28 上线）

- **目标**：Worker 订阅只做"换入口 IP"，所以优选判据是"这个 IP 能不能承载 `SNI=goui.290490.xyz`"，不是"IP 快"。
- **电脑侧**（`06-CF优选/cfopt.py`，手动，单轮约 1 分钟）：`ranges`（CF 官方 15 条 v4 网段，7 天缓存）→ `pool`（9 源并发，≥2 源成功才继续，非 CF 段直接拒）→ `probe`（TCP → **TLS SNI+证书校验** → **WS 升级 101/200**，A/B/C 三段）→ `colos`（取真实 colo 打标签）→ `emit`（`yx.txt` / `mihomo_proxies.yaml`）→ `upload`（写 Worker KV `yx`，回读校验）→ `verify`（线上订阅 `ALL_IN_CF=1`）。
- ★ **探测必须临时旁路**：本机流量被 `dstnat` 透明代理，直连探测才有意义。脚本在 `inet nikki dstnat` 顶部插 `ip saddr 192.168.31.218 tcp dport 443 return`（注释 `cfopt-probe-bypass`），结束/异常都会删；判据是"到 CF 边缘 TCP RTT ≥4ms"（旁路生效时 240–290ms，未生效 1.5ms）。
- **路由器侧**（`/usr/local/bin/cf-refresh.sh`，cron 04:17，40h 门控）：`curl` 面板订阅 → awk 校验（节点数 ≥5、每个 `server` 命中 `/etc/cf/cf_v4_ranges.txt`、`servername` 全对、无 `ech:`）→ 写 `.new` 再 `mv`（原子）→ `PUT /providers/proxies/CF优选` 重载（`reloaded=api:204`，无中断；失败退回 `/etc/init.d/nikki reload`）。实测 1–2s，内存 +1MB，无 OOM。
- **接线**：profile 里 `CF优选`（`type: file`，`path: /etc/nikki/run/providers/cf-optimized.yaml`）已并入 `♻️ 香港自动`（url-test）/`🇭🇰 香港节点`（select）/`🌐 全部节点`（select）；**2026-10-29 已删除原 `♻️ CF自动` / `🇨🇫 CF节点` 两个独立分组**（用户要求，`🚀 默认代理` 不再单列 CF 组）。节点名 `[CF] HK-n`。
- ★ **file provider 的 path 必须在 `/etc/nikki/run` 下**：放 `/etc/nikki/providers/` 会报 `path is not subpath of home directory or SAFE_PATHS ... allowed paths: [/etc/nikki/run]`，core 直接起不来（`active with no instances`）。
- **标签规则**：colo 命中 `SIN` → `SG-n`，其余一律 `HK-n`。实测本机到 CF 的落点是 **HKG / SJC / LAX（150 个抽样里 0 个 SIN）**，所以全标 HK；CF 组定位**备用**（实测 8 Mbps / RTT 240–600ms），主力仍是机场。
- 回滚：`/root/bak-cfopt-20261028-152430/`（profile+cron+uci）；上传侧 `cfopt.py upload --rollback`（用 `state/yx.prev.txt`）；停自动刷新删 cron 那行即可。

### 4.7 sniffer / mixin 控制面（★ profile 里写 sniffer 段无效）

- Nikki 每次启动都用 `/etc/nikki/ucode/mixin.uc` **无条件生成 `sniffer` 段覆盖 profile**（同理覆盖 `dns.listen/ipv6/enhanced-mode/fake-ip-range`、`port/redir-port/tproxy-port`、`tun`、`external-controller/secret`）⇒ 改 sniffer **只能改 uci**：`uci set nikki.mixin.sniffer=1 && uci set nikki.mixin.sniffer_sniff=1 && uci commit nikki` 后 restart。
- 2026-11-03 定值（fake-IP 下唯一有意义的用法）：`force-dns-mapping=0`（fake-IP 下是死配置）、`parse-pure-ip=1`（只给 real-ip 纯 IP 连接补域名做规则匹配）、`override-destination=0`（**不改写目标**，否则 DIRECT 出站再解析一次、纯 IP 流被"升级"成域名流，可能换到境外 CDN 节点）、QUIC 嗅探关闭。
- ★ **LuCI 选"不修改"= 删掉该 uci 选项 = mixin 不覆盖该字段**（`ucode/include.uc` 的 `trim_all` 只删 null，`uci_bool(nil)` 返回 null 而非 false）——所以"不修改"安全；反之 **LuCI 整页保存会删掉显示"不修改"的手工 uci 项**：2026-11-03 18:00 一次 LuCI 保存就抹掉了 `sniffer_sniff_dns_mapping/pure_ip`、把 `udp_mode` 改成 tun、`ipv6_proxy` 改成 0，已按内核实际能力恢复（UDP 回 tproxy、IPv6 代理按用户要求关）。
- ★ Nikki 生成的 sniff 段键名是 `port`，mihomo 认的是 `ports`（`RawSniffingConfig{ Ports []string \`yaml:"ports"\` }`，wiki `/config/sniff/` 示例 `TLS: ports: [443,8443]`）⇒ **静默失效**、回落到协议默认端口（HTTP 80 / TLS·QUIC 443）。**2026-11-10 20:05 已修**：`uci set nikki.mixin.mixin_file_content=1`（让混入文件参与合并）+ `/etc/nikki/mixin.yaml` 里补 `sniffer.sniff.{HTTP,TLS}.ports`，深合并后与 ucode 生成的旧 `port` 键共存、由 `ports` 生效；**不要用 LuCI 混入页整页保存**（会把 `mixin_file_content` 复位成 0，修复随之失效）。
- ★ **TUN 关闭是安全的（2026-11-03 晚）**：`uci set nikki.mixin.tun_enabled=0` 后 mixin 生成 `tun.enable: false`，`ip link show nikki` 为空；`/etc/init.d/nikki` 只在 `tcp_mode=tun` 或 `udp_mode=tun` 时才检查 TUN 设备，当前是 redirect+tproxy ⇒ 不受影响。


---

## 5. DSH 手机端远程入口

- 地址：`https://dsh.290490.xyz:3081`（Cloudflare 上 `dsh` 的 AAAA 为 **DNS-only**，指向 `pppoe-wan` 的公网 IPv6）
- 路由侧：`/etc/dsh-nginx/` 独立 procd（nginx `[::]:3081` TLS + **Host 强制改写** + **HTTP/2**）→ 反代 PC `192.168.31.218:<实际端口>` 的 DSH Pocket；上游写在 `/etc/dsh-nginx/upstream.conf`，由看门狗维护
- 证书：`acme.sh`（Let's Encrypt **DNS-01**，Cloudflare，token `/etc/cf-dns.token`）→ `/etc/dsh-nginx/cert/`
- DDNS：`ddns.dsh_ipv6` + `/usr/lib/ddns/update_cloudflare_dsh.sh`（**每 30 分钟**轮询 + `95-ddns` 在 ifup 时立即触发；IP 只在重拨/重启变，2026-11-01 从 5 分钟降频；另每 12 小时对账一次线上记录）
- ★ **重拨后 mihomo 会缓存旧 AAAA（2026-11-03 实测）**：mihomo 的 fake-ip 双向映射对 `dsh.290490.xyz` 这类 real-ip 域名会**钉住重拨前解析到的 IP**（实测 Cloudflare 记录与 223.5.5.5/119.29.29.29/doh.pub/dns.alidns.com 全是新值，只有 `curl 127.0.0.1:9090/dns/query?name=dsh.290490.xyz&type=AAAA` 返回旧值且 TTL=1）⇒ 客户端连旧地址，外网入口 000/超时。修复：重启 nikki（约 5s 抖动）即可；现已装 `/usr/bin/dsh-dns-guard.sh`（cron `*/15`，比对 mihomo 应答 vs `pppoe-wan`；不一致时 **2026-11-10 新增第一档 `POST /cache/dns/flush` → 复查**，仍不一致再 `PUT /configs` 重载，最后才重启 nikki（原逻辑 reload 无效就重启，15s 中断）；日志 `/var/log/dsh-dns-guard.log`），并写进 `/etc/sysupgrade.conf` keep。**2026-11-10 20:05 起 `dsh` 改用 `223.5.5.5/119.29.29.29` 解析（profile `nameserver-policy` 首条），实测解析源从 `udp://192.168.31.1:53` 变为 `udp://223.5.5.5:53`、AAAA 与 `pppoe-wan` 一致、外网入口 `curl -6 dsh:3081` 200/1.22s**。**排查判据**：记录对、WAN 对、但 `dsh` 打不开 ⇒ 先看这个缓存。
- 防火墙：`Allow-DSH-Pocket-IPv6`（wan→tcp/3081 ACCEPT，仅 IPv6）
- **为什么必须走 nginx**：DSH Pocket 的 `classifyHost()` 把裸 IPv6 Host 当 loopback 免密；nginx 改写 Host 后，IP 直连也只能看到 PIN 页
- ★ **Pocket 端口会漂（2026-11-01 事故）**：DSH Pocket 默认 3081，启动时被占会 `+1..+9`；当天 DSH 16:11 重启后落到 **3082**，nginx 仍指 3081 ⇒ 本机 8 秒后 502；同时有两条未记录的 DNAT（wan 3081/3082 → PC 的 IPv6）抢在 nginx 前把流量劫到 PC，而 Pocket 只监听 `0.0.0.0`（IPv4）⇒ 外网一律超时。**已删 DNAT**；PC 侧 `settings.json` 写入 `"proxyPort": 3081`（下次 DSH 重启生效）；路由器看门狗每 5 分钟探测，**只探当前端口，探不通才扫 3081–3084（扫描 10 分钟节流）**，漂移时自动改写 upstream 并 reload
- ★ **不要再给 3081/3082 加 DNAT**：会绕过 TLS/Host 改写，而且 PC 的 IPv6 是 RA/SLAAC，前缀一换就失效
- ★ **nginx 性能/稳定性（2026-11-01 实测）**：`http2 on`（ALPN=h2，外网 VPS TTFB 0.22–0.31s）、`/assets/` 一年 immutable 缓存、gzip（HTML 42670→2074 B）、上游 keepalive、`proxy_connect_timeout 2s`、删掉已下线的 `.222` 备份（故障时曾多等 5 秒）
- ★ **nginx 启动依赖 `/var/lib/nginx`（tmpfs，重启即丢）**：独立 init 的 `start_service()` 必须先 `mkdir -p /var/lib/nginx/{body,proxy,fastcgi,uwsgi,scgi}`，否则重启后 nginx 报 `mkdir() "/var/lib/nginx/body" failed` 直接退出 ⇒ 3081 无监听（2026-10-27 事故：DDNS 正常但入口打不开，被误判成 DDNS 失效）
- ★ **看门狗**：`/usr/bin/dsh-watchdog.sh` + cron `*/5 * * * *`（2026-11-01 从 `*/2` 降频）—— nginx 不在就 `restart`；`dynamic_dns_updater` 不在就后台拉起（`-S <section> -- start` 是前台常驻，**必须加 `&` 放后台**，否则 cron 卡死）；端口自动发现；`pppoe-wan` 的 IPv6 与 `/etc/dsh-ddns-last` 持续 15 分钟不一致 → 告警并重启 ddns；证书 <14 天告警（每小时）；单实例锁防重叠；**端口变更 reload 后做一次本地 HTTPS 探针（`Host: dsh.290490.xyz` → `[::1]:3081`），非 200/302 则自动 `restart`**（2026-11-01 实测 OpenSSL 偶发 `SSL_CTX_new` emerg 会让 reload 静默失效、旧 worker 继续用旧上游）
- ★ **DDNS 重拨存活**：`ddns.dsh_ipv6.retry_max_count=0`（无限重试）。原值 3 会在重拨瞬间 `pppoe-wan` 无地址时连续失败 3 次后自杀，只等 hotplug ifup 捞回（不保证）
- ★ **PC 侧**：DSH **没有设开机自启**（Windows 重启/更新后需手动打开，否则入口快速 502）；DSH 更新/重启后 Pocket 端口若变（3081↔3082），watchdog ≤5 分钟自愈，想立刻恢复执行 `python ssh_run.py '/usr/bin/dsh-watchdog.sh'`
- ★ **刷机后恢复（2026-10-29 于 R26.10.29 实测）**：sysupgrade 只保 keep 内的 `/etc` 文件与 `/etc/nikki`。三件事：
  1. **nginx-ssl / libpcre2 / libxml2-16 包会丢**（`/usr/sbin/nginx` 不存在 ⇒ 3081 无监听）→ `sh /usr/bin/dsh-restore.sh`（幂等；2026-11-01 实测：装包 + 建 tmpfs 目录 + 补 upstream.conf/port + cron/keep + `nginx -t` 检查；输出 `nginx running / 3081 listening / ddns running / token+cert present / local 200`）。**更新/刷机/Windows 重启后的完整行为表见 `04-代理-nikki/dsh-pocket-ipv6/README.md` §10**
  2. **CF 优选链路整条丢**（`/etc/cf/` 与 `/usr/local/bin/cf-refresh.sh` 原不在 keep，但 cron 那行还在 → 每天 04:17 静默失败）→ 已补进 keep；PC 侧 `python tools/restore_cf_after_flash.py` 一键重建并 `DRY` 自检（期望 `DRY ok nodes=N`）
  3. **PC 侧 IPv6 旧前缀残留**（重拨后旧 /64 失效）会让 `curl -6 https://dsh...` 超时/`000`，删掉旧地址或重连网卡即可（判据：PC 能 ping 通 `ip -6 addr show pppoe-wan` 的地址）

---

## 6. 性能基线与测量方法

**当前基线（QWRT R26.11.10 / 内核 5.4.302，2026-11-10 实测；offload = 软件 `1/0`，flowtable = `{br-lan, pon0.995, pppoe-wan}`）**
- 用户侧实测口径（2026-11-10 复核，PCIe 1GbE 网卡计数器为准）：**软件卸载 948–968 Mbps（= 网卡线速上限）**；同一时刻切硬件卸载只有 **630–671 Mbps**。★ curl 自报的 `speed_download` 多流求和会虚高（实测 1300+ Mbps > 1GbE 线速），**别用 curl 之和当带宽，用 `Get-Counter '\Network Interface(*)\Bytes Received/sec'` 交叉验证**。
- 2026-11-06 用 speedtest.cn 上海联通测过：无卸载 1,026 / 软件 1,022 / 硬件 632 Mbps（同一结论）。
- 2026-10-29 PC 侧多源脚本（`tools/wan_speedtest.py`）因镜像端限速只取到 190–480 Mbps 的波动值，**未构成可信基线，待重跑**。

**历史基线（内核 5.4.302 / R26.10.25，2026-10-27 测得 —— 仅存档，勿套用）**

| 场景 | 结果 |
|---|---|
| 单站点 10 条流（bfsu） | **914 Mbps 中位**（907/926/914/926），峰值 926 |
| 多源 6 站点 × 3 条流 | **984 Mbps** |
| 饱和时路由器 CPU | **≈29%**（4 核，softirq 为主） |
| 软卸载关闭（全关） | 845 Mbps 中位 |
| ★ 硬件卸载开启 | **640 Mbps 中位**（本机 600M 事故的真因） |
| 单站点单流上限 | 210–230 Mbps（站点/BDP 限制，不是线路） |

**测速方法（重要）**：不要用单站点测速下结论。用 **6–10 个不同国内镜像，每站 1–2 条流，跑 15 秒**看聚合值。`speedtest.cn` 的静态资源 CDN 实测只有几 Mbps，不能当源。

**代理吞吐**：受机场/自建 VPS 限制（机场 HK 约 130–150Mbps；自建 SG TLS 握手 0.85–2.2s）。**直连能跑满千兆不等于代理也能**。

**API 线路基线（2026-11-07，经代理 10 次采样）**：`opencode.ai/zen/go/v1/models` TLS p50 0.36s / TTFB p50 0.70s（改前 0.80/1.31）；`amr-link.open-design.ai/v1/models` TLS 0.33s / TTFB 0.70s（401）；colo 均 SIN。同源 2MB 实测 12–22 Mbps（`🚀 默认代理`）。

---

## 7. 已知问题与判据（踩坑沉淀，★ 必看）

### ★1 任何 flow offload 都会压死下行（600M 事故；2026-10-29 升级为「必须无」）
- 现象：千兆线路只能跑 ~600，且 CPU 不高、无丢包
- **内核 7.3（R26.10.29）实测：`flow_offloading=1` 的软件卸载与 `hw=1` 的硬件卸载都只有 ~600M；只有全关（`0`/`0`，即 LuCI 选「无」）才满速**
- 原因：7.3 的 `an7581_bsp_ppe.ko` 依赖 `nf_flow_table`/`br_netfilter` 并替换 `nf_flow_offload_{ip,inet}_hook`，会接管 flowtable 条目，但模块没有 PPPoE 封装能力 ⇒ 只要存在 flowtable，PPPoE 流就被拖进半残快路径
- 历史（5.4.302 / R26.10.25-26）：`hw=1` 640M、`=1/0` 914M、全关 845M —— **旧结论已反转，别再引用**
- 铁律（7.3 起）：**`flow_offloading=0` + `flow_offloading_hw=0`**；`nft list table inet fw4 | grep -c flowtable` 必须为 `0`
- **判据**：遇到"千兆只跑 600"，**先看 flowtable 是否为 0**，再怀疑测速站和线路

### ★2 GOMEMLIMIT 字段必须留空
- `luci-app-nikki` 把 `env_go_mem_limit` 声明成 `datatype='uinteger'`，而 Go 的写法是 `80MiB` ⇒ `parseInteger('80MiB')=NaN` ⇒ **整个 nikki 页面（Map 级）保存被拒，连"关 nikki"都存不了**
- 已 `uci delete nikki.procd.env_go_mem_limit`；**该字段永远留空**
- **陷阱**：填纯数字（如 `150`）会被 Go 当成 **150 字节** → GC 风暴；填乱码 → 启动 panic。要设限只能 SSH 写 `140MiB` 这类带单位值，且之后 LuCI 保存会再报错
- 附带：原来 `80MiB` 软上限低于实际堆（VmHWM 108MB）→ 长期贴上限 GC；去掉后 VmRSS 95→87MB、MemAvailable +8MB

### ★3 内网主机名靠 `+.lan` 策略，不是 dnsmasq
- LAN `:53` 被劫持到 mihomo，**dnsmasq 完全不参与客户端解析**；mihomo 只读 `/etc/hosts`，不认识 DHCP 租约
- 所以 profile 里 `nameserver-policy: "+.lan" → 192.168.31.1` 是刚需（mihomo 自己的查询有 cgroup 豁免，不会回环）
- **排查陷阱**：在路由器上 `nslookup xxx.lan 127.0.0.1` 也 NXDOMAIN —— root 查询同样被劫持到 1053，看起来像 dnsmasq 不认识租约，其实查询没到 dnsmasq

### ★4 境外 DoH/DoT 不要经代理：已根治（2026-11-03）
- 历史：`tls://8.8.4.4:853` 经 `🐟 漏网之鱼 → 🚀 默认代理 → ♻️ 香港自动` 反复失败（core.log 120+ warning，还会把 `香港自动` 判 failed 触发 re-test），换成 `https://dns.google/dns-query` 只是绕开症状。
- 现在：`respect-rules: false` + 上游全国内直连 ⇒ DNS 连接**不进规则表、不经代理**（`tunnel/dns_dialer.go`：proxyName 为空直接 `dialer.DialContext`），该类故障不会再出现。**不要再把境外 DoH/DoT 写回 `nameserver`**（关了 respect-rules 它会被直连→污染/超时）。

### ★5 fake-ip 例外判据
要加 `real-ip` 例外，**先证"真实 IP ∈ `@china_ip`"**，否则零收益。反例：`cn.download.nvidia.com` 真实 IP 是 Akamai `2.22.242.x`（不在 CN 段），强推直连只会更慢；`www.nvidia.cn` 才是国内 IP（内核已直连）。

### ★6 fake-IP + `GEOIP,CN,...,no-resolve` ⇒ 国内站点被误送进代理（2026-10-30 MatchBest 登录事故）
- **现象**：`https://app.matchbest.co` 页面能正常打开，但点「登录」必失败；浏览器网络面板里 `POST https://vipapi.tradepower.net/v1/account/login_sp` = **`net::ERR_CONNECTION_CLOSED`**，路由器上 curl 同一 URL 报 `TLS alert, decode error` / `unexpected eof while reading`
- **原因链**：`vipapi.tradepower.net` 真实 IP **39.99.205.168**（阿里云杭州，属 `@china_ip` 的 `39.98.0.0/15`）；但 LAN 客户端拿到的是 fake-IP（`198.18.7.216`），而规则 `GEOIP,CN,🎯 直连,no-resolve` **带 `no-resolve` 就不会为域名去解析**，fake-IP 当然不属 CN ⇒ 落到 `MATCH,🐟 漏网之鱼` ⇒ 香港机场节点去连国内 API，TLS 被直接掐断
- ★ **源码级更正（2026-11-03）**：fake-IP 连接在跑规则前就被 `preHandleMetadata` 反查成域名并**清空 DstIP**，所以 `GEOIP,...,no-resolve` 拿到的是无效 IP、`Match` 直接 `return false` —— 不是"判错归属"，而是**恒不命中**；同理 `AND,...,(NOT,(GEOIP,CN,no-resolve))` 在 fake-IP 下等价于"条件恒真"（QUIC 规则曾踩过，见 §4.4-3）
- **判据（最快）**：`curl --resolve vipapi.tradepower.net:443:39.99.205.168 https://vipapi.tradepower.net/` —— 绕过 fake-IP、由内核 `@china_ip` 直通，**能通**（返回 `403` 也算通）；同一 URL 走 fake-IP 不通 ⇒ 是路由问题，**不是站点或密码问题**
- **定位 rule match**：把 mihomo 日志级别临时调到 info（`PATCH http://192.168.31.1:9090/configs`，`Authorization: Bearer <secret>`，body `{"log-level":"info"}`，用完改回 `warning`），复现一次即可看到 `match Match using 🐟 漏网之鱼[[吹雪] 🇭🇰香港•移联01]`
- **修法（2026-10-30 定稿：规则归 `zdcn` 列表管理，profile 不硬编码）**：域名条目写进 GitHub `Bernardxu123/xu` 仓库的 **`zdcn.list`**（`DOMAIN-SUFFIX,tradepower.net`），路由侧只靠 `RULE-SET,zdcn,🎯 直连`（§4.4-6）生效。生效三步：① GitHub 提交 → ② `https://purge.jsdelivr.net/gh/Bernardxu123/xu@main/zdcn.list` 刷 CDN → ③ `PUT http://192.168.31.1:9090/providers/rules/zdcn`（`Authorization: Bearer <secret>`，返回 204）强制重载，再 `cat /etc/nikki/run/providers/rule/zdcn.list` 确认。实测 `match RuleSet(zdcn) using 🎯 直连[DIRECT]`、API `HTTP 200`/0.2s。回滚 `/root/bak-zdcn-20261030/profile.yaml`
- ★ **镜像坑：`testingcf.jsdelivr.net` 不认 purge**——`purge.jsdelivr.net` 返回 `finished`，它仍继续发 12h 的旧 `@main` 缓存（同时刻 `cdn`/`fastly`/`gcore` 三个镜像都已是新内容，只有 testingcf 是旧的）⇒ 2026-10-30 把 `zdcn` 的 url 从 `testingcf.jsdelivr.net` 换成 **`cdn.jsdelivr.net`**（可 purge；路由器侧实测两者同为 0.43s）。`zdgw`/`oracle` 仍用 testingcf，将来要"立刻生效"时照此换。另：**URL pin 到 commit sha（`@<sha>`）时所有镜像都立刻是新的**，可用来判断"到底更没更新"
- **结果（2026-10-30）**：修完后浏览器端到端登录成功、仪表盘正常加载。顺带记下三个响应签名，以后好区分「网络不通」和「密码错」：成功 `{"code":200,"result":{...}}`；账号/密码不符 `{"code":201,"message":"用户名或密码错误"}`；参数缺失 `{"code":202,"message":"缺少必要的参数[...]"}`。**注意 `ERR_CONNECTION_CLOSED` 只可能是网络层（规则/节点），跟密码无关**
- **教训**：**凡是「国内 IP 但域名不在 `oc-cn-domain` 里」的站点都会踩这个坑**（`no-resolve` 让 `GEOIP,CN` 对 fake-IP 全线失效）。别急着怀疑账号密码，先按上面判据验证直连。工具：`tools/fix_tradepower_direct.py`（先期把规则硬编码进 profile）+ `tools/move_tradepower_to_list.py`（最终把规则搬进 zdcn 列表、并把 CDN 换成 `cdn.jsdelivr.net`）；两者都走 exec_command 传文件（路由器既没 sftp 也没 base64）

### ★7 DSH Pocket 端口漂移 + 不要给 3081/3082 加 DNAT（2026-11-01）
- **现象**：公网 `https://dsh.290490.xyz:3081` 502/超时；nginx error.log 报 `upstream timed out` 与 `.222 Host is unreachable`（8 秒才 502）；外网 VPS 测 3081/3082 全超时
- **根因两条**：① DSH Pocket 默认 3081，启动时被占会 `+1..+9`（当天 DSH 16:11 重启后漂到 3082），nginx 却写死 3081；② firewall 里另有两条 DNAT（wan 3081/3082 → PC 的 IPv6）抢在 nginx 前劫持，而 Pocket 只监听 `0.0.0.0`（IPv4）⇒ IPv6 DNAT 永远连不上
- **判据**：PC `netstat -ano | findstr :308` 看实际端口；`nft list chain inet fw4 dstnat_wan | grep -E 'dport (3081|3082)'` 应为空；`nft list chain inet fw4 input_wan | grep 3081` 计数应随外网访问增长
- **修法**：PC `%USERPROFILE%\.dsh\dsh-pocket\settings.json` 加 `"proxyPort": 3081`；路由器 watchdog 每 5 分钟探测并自动改写 `/etc/dsh-nginx/upstream.conf`；DNAT 删除，只保留 `Allow-DSH-Pocket-IPv6`
- ★ **探测必须用 curl**（`--connect-timeout 1 -m 3`）：PC 未监听端口会被 Windows 防火墙静默丢包，BusyBox `wget -T` 不覆盖 connect，会挂到 TCP 超时（当天 watchdog 卡死、进程堆积的根因）

### ★8 协议选型实测：Reality 不可用，生产保留 TLS（2026-11-06）

- **目标**：在 Oracle SG 1C VPS 上对比 REALITY / VLESS Encryption / Hysteria2 / VLESS+TLS，选出路由器（mihomo 1.19.33）最合适的节点协议。
- **REALITY 失败**：3x-ui `新加坡2`（20894）新增 `router-vision` 客户端（flow `xtls-rprx-vision`），mihomo 节点握手时 debug 打印 `REALITY Authentication: false`，delay 503；同一套 UUID/publicKey/shortId/serverName 用 Xray 26.10 客户端从 VPS 本机连 `127.0.0.1:20894` 返回 **204**（XtlsFilterTls found tls 1.3 + splice），证明服务端参数正确。已排除：去掉 flow、换 4/8/16 位 shortId、去 xudp、firefox/ios 指纹、`timeline.www.cloudflare.com`、以及另起一套全新 Reality 服务端——mihomo 均 503。**结论：本机 mihomo 的 REALITY 客户端与 Xray Reality 服务端不兼容**；节点已从 profile/run 删除，3x-ui `router-vision` 客户端保留便于以后 Xray 客户端/修复复用。
- **VLESS Encryption**：`xray vlessenc` 生成 X25519/ML-KEM-768 两套 `decryption`/`encryption`，独立 Xray 服务端（2095）+ mihomo `encryption` 客户端；`mihomo -t` 通过、热重载 204，但 delay 503；暂不上生产。
- **Hysteria2**：delay gstatic **96–101ms**、opencode.ai **274–281ms**；但经默认代理下载 `speed.cloudflare.com` 50MB 两次 `speed_download=0`（56s/5s），5MB 报 `schannel: failed to receive handshake`（21.8s）——本链路 UDP/QUIC 对 bulk HTTPS 不稳定，保留备用。
- **VLESS+TLS 8443**：delay gstatic 122–257ms、opencode.ai 278–435ms；50MB 下载 4.34s/5.17s → **10.1–12.1 MB/s（约 81–97 Mbps）**，稳定无错误。`🛡️ 稳定固定` 继续选 `🇸🇬 新加坡-自建TLS`。
- **主瓶颈**：家到 VPS RTT ≈**232ms**；协议优化消不掉，追求低延迟优先换 HK/JP VPS 或机场 HK 节点。
- **回滚/备份**：VPS `/root/bak-proto-20261106-102524/`（x-ui.db/config.json）；路由 `/root/bak-proto-router-20261106-103242/`、`/root/bak-proto-cleanup-*`；当前 profile 22,142B/593 行、sha256 `ad5b5435…`、规则 74/组 18（vlook 并入 Learn 后）。

### ★9 Google Play「能看不能下」：gvt1/dl 被 google-cn 抓成 IPv6 直连（2026-11-06）

- **现象**：Play 商店能打开、能看到软件，但下载/更新卡住或失败；`play.googleapis.com`/`android.clients.google.com` 等 API 域名是 fake-IP（198.18.x）且走代理，所以列表能加载。
- **根因**：`dl.google.com`、`redirector.gvt1.com`、`*.gvt1.com` 被 `GEOSITE,google-cn` 的 `fake-ip-filter ... real-ip` 抓成**真实联通 IPv6**（实测 `2408:80f1:1b0:109::1001`）；而 IPv6 代理是关闭的，客户端走 IPv6 直连到该地址，Play 的 APK 下载失败。
- **修法**：① 规则（排在 `GEOSITE,google-cn` 之前）：`DOMAIN-SUFFIX,gvt1.com`/`gvt2.com`/`gvt3.com`/`dl.google.com` → `🚀 默认代理`；② DNS `fake-ip-filter` 顶部加同名 `...,fake-ip`，覆盖 google-cn 的 `real-ip`，让域名拿 198.18.x、AAAA 变 NODATA；③ 规则 58→62。
- **实测**：DNS `dl.google.com`/`redirector.gvt1.com`/`gvt1.com` → 198.18.x；`curl -4 https://dl.google.com/android/repository/repository2-1.xml` → 200；8MB `platform-tools-latest-windows.zip` 0.97s（约 66Mbps）；`redirector.gvt1.com` 已走代理（404 为正常根路径）。
- **注意**：手机/平板可能还缓存旧 IPv6，重连 Wi-Fi / 重启 Play 商店或设备后再试；若仍慢，可把 `🚀 默认代理` 临时切到 `🛡️ 稳定固定` 或 `🌐 全部节点`。
- **备份**：`/root/bak-play-20261106-110106/`（profile+run）。
- **2026-11-06 15:35 并入 AI 组**：Play/Gemini 全部域名（含 `play.googleapis.com`/`play.google.com`/`play-fe`/`android.clients`/`clients3`/`content-push`）统一 → `🤖 AI`；`GEOSITE,google` 仍 `🌐`。规则 68→74；实测上述域名均匹配 `🤖 AI[[顺畅] 🇯🇵日本-原生01]`。以后只切 `🤖 AI` 组即可同时调整 Play + Gemini；备份 `/root/bak-ai-google-20261106-153511/`。
- **UDP/443 证据**：日志抓到手机 Play 的 `rr4---...xn--...:443` UDP 命中通用 QUIC `AND(...) REJECT`；这是下一步要处理的重点（建议只给 Play 下载域名加 UDP 例外，不删通用 QUIC 规则）。
- **DNS 实测**：`netstat` 只有 dnsmasq:53 + mihomo:1053，无 7874；nft `lan_dns_hijack` 把 LAN :53 直接 redirect 到 :1053，dnsmasq 对 LAN 实际被绕过（不是 dnsmasq 转发 1053）。
- **Gemini**：`🤖 AI → 🌐 全部节点` 后 exit IP 实测 `160.16.55.155`（东京），页面仍提示“不支持你所在的地区”，更像账号/ cookie/地区判定，不是链路；需另查 Google 账号地区。
- **2026-11-06 14:35 追加（@china_ip 内核 bypass）**：`clientservices.googleapis.com`/`services.googleapis.cn` 实测解析到 `211.95.34.129/139`，`nft get element inet nikki china_ip` 命中 `211.80.0.0/12` ⇒ 内核 `ip daddr @china_ip counter return` 排在所有 redirect 之前，mihomo 规则根本看不到，`GEOSITE,google` 的代理规则失效。已加 `fake-ip` 前置覆盖 + 显式 `🚀 默认代理`，DNS 变 `198.18.x`、curl 走代理；`googleapis.cn` 本身 NXDOMAIN 无 A，未加。rules 62→64，备份 `/root/bak-google-20261106-143437/`。

- **2026-11-06 15:40 结论：暂不加 Play 的 UDP/443 例外**：Play 已能正常更新（TCP 走 `🌐 全部节点`；QUIC 仍被通用 REJECT，但 TCP 回退正常）。当前机场日本原生节点的 UDP 质量未验证，开放 Play QUIC 可能反而卡住；保持通用 QUIC REJECT，若再次出现更新卡住，再定向给 `xn--...` 加 UDP 例外。

### 其他常备事实
- 现固件**有** `nft_tproxy`（UDP tproxy 在用）；**仍无 zram，仍不能 swap**（ubifs）
- ★ **刷机后 QWRT 会把 telnetd / vsftpd / samba 恢复为开机自启**（明文 21/23/139/445，samba 约 12MB 内存），另有陈旧 DNAT/openvpn 入站规则也可能回归：每次刷机后执行 `/etc/init.d/{telnetd,vsftpd,samba,miniupnpd} disable; … stop`，并检查 `nft list chain inet fw4 dstnat_wan`（除 fullcone 外应为空）与 `input_wan` 是否多出 1194。判据：`netstat -lntup | grep -E ':(21|23|139|445) '` 为空
- MTU：`wan.mtu` 保持 1500，协商 1492；不要填 1492
- 9090 面板 secret 6 位且 `allow_lan=1`，属**待加固项**
- 不要手改 `/etc/nikki/mixin.yaml`（ucode 会覆盖），用 `uci set nikki.mixin.*`
- sniffer 生效需要 `mixin.sniffer=1` **且** `mixin.sniffer_sniff=1`
- IRQ 全落 CPU0，但饱和时 CPU 仅 29% ⇒ **不需要动 IRQ/RPS**
- `bypass_china_mainland_ip`（内核 nft）与 profile 里的 `GEOIP,CN` 规则是**两套机制**；前者命中后规则表根本看不到这些流量
- ★ **IPv6 代理已关（`ipv6_proxy=0`）且 profile 删除了 `fake-ip-range6`**（2026-11-03，用户要求）：境外 AAAA → **NODATA**（不再下发 `2001:2::x`，避免双栈设备连一个不被代理的假 IPv6 形成黑洞）；国内域名与 `dsh.290490.xyz` 的真实 AAAA 由 fake-ip-filter 保证。恢复 IPv6 代理必须**成对**改：`uci set nikki.proxy.ipv6_proxy=1` + 把 `fake-ip-range6: 2001:2::1/64` 加回 profile
- ★ **`nameserver-policy` 多个服务器是"并发取最快"、且 NXDOMAIN 也算成功响应**（`dns/util.go batchExchange`）：别把 `192.168.31.1` 和 `223.5.5.5` 塞进同一个值，否则公网 DNS 的 NXDOMAIN 会随机抢答 `*.lan`；要 ISP 就近效果就只放 dnsmasq 单值
- ★ **不要写 `direct-nameserver`**：它会独占 DIRECT 出站解析，而 nikki mixin 把 `direct-nameserver-follow-policy` 固定为 false ⇒ `nameserver-policy` 对 DIRECT 拨号失效（`tablet.lan` 会被公网 DNS 解析成 NXDOMAIN）。不写 = DIRECT 解析走主 resolver + policy
- ★ **mihomo yaml 不校验未知字段**：`sniff.HTTP.port`（正确键是 `ports`）、`dns.cache-algorithm: lru`（v1.19.32+ 只认 `arc`）都是静默失效。改完必须看 `/etc/nikki/run/config.yaml` + `mihomo -t`，别只看"能启动"
- ★ **zdcn 必须与 fake-ip-filter/policy 成对**（2026-11-03 晚）：只加 `rules: RULE-SET,zdcn,🎯 直连` 不够——域名若拿 fake-IP 就要进 mihomo 用户态、且解析走 223.5.5.5。必须同时 `dns.fake-ip-filter: - RULE-SET,zdcn,real-ip` + `nameserver-policy: "rule-set:zdcn": [192.168.31.1]`，才能拿真实国内 IP 并在内核 `@china_ip` 层零开销直通（`tradepower.net` 即此闭环）
- ★ **provider `health-check.interval` 是 `use:` 型组延迟数据的唯一来源**（2026-11-03 晚 1800→600）：组的 `interval` 对 `use:` 组不生效；改完确认 `yq -M '.proxy-providers[]."health-check".interval'` = 600/600/600
- ★ **UDP 用 tproxy，不要用 TUN**（2026-11-03 复核）：`nft_tproxy.ko` 在（`/lib/modules/7.3.1/`）、nft 内已有 `tproxy to :7892`；TUN 走用户态 gvisor 反而更费 CPU/内存（`udp_mode` 只在 LuCI「透明代理」页或 `uci set nikki.proxy.udp_mode=tproxy` 改）

---

## 8. 运维手册

### 8.1 连路由器
```powershell
python ssh_run.py 'uci show firewall | grep offload'          # 单引号包远程命令
python ssh_run.py 'cmd1' 'cmd2'                                # 多条
```

### 8.2 改代理配置的标准流程
```sh
# 1 备份（uci + profile + 运行时三件一起备）
mkdir -p /root/bak-<主题>-$(date +%Y%m%d); D=/root/bak-<主题>-$(date +%Y%m%d)
cp /etc/nikki/profiles/openclash-20261022.yaml $D/profile.yaml
cp /etc/nikki/run/config.yaml                  $D/run-config.yaml
cp /etc/config/nikki                           $D/uci-nikki.conf; uci show nikki > $D/uci-show.txt
# 2 改源 profile（不要改 run/config.yaml，会被重新生成；sniffer/端口/DNS listen 只能改 uci）
# 3 上机前自测（复刻 nikki 管线：del(.sniffer.sniff) → mixin 合并 → tun 修正 → mihomo -t）
sh tools/deploy_nikki_opt_20261103.sh          # 备份→改uci→自测→(通过才)安装+重启；失败自动回滚
# 4 验证
/etc/init.d/nikki status; pidof mihomo
grep -cE "level=(error|fatal)" /var/log/nikki/core.log
yq -M '.rules | length' /etc/nikki/run/config.yaml          # 2026-11-06 起应为 74
nslookup www.baidu.com 192.168.31.1                          # 真实国内 IP
nslookup www.google.com 192.168.31.1                         # 198.18.x
# 5 需要看"到底命中哪条规则/走哪台上游"时，临时开 debug 再关：
curl -s -X PATCH -H "Authorization: Bearer <secret>" -H "Content-Type: application/json"   -d '{"log-level":"debug"}' http://192.168.31.1:9090/configs
grep -aE "match |\[DNS\] resolve" /var/log/nikki/core.log | tail -20
curl -s -X PATCH ... -d '{"log-level":"warning"}' ...          # 记得改回
```
★ **LuCI 保存 Nikki 页面 ≠ 无副作用**：页面保存会写入表单字段并**删掉显示"不修改"的手工 uci 项**（例：`sniffer_sniff_dns_mapping`/`sniffer_sniff_pure_ip`），也可能把你手改过的 `udp_mode`/`ipv6_proxy` 一起覆盖。改完 uci 后如果要进 LuCI 看，**只看不点保存**。

### 8.3 备份 / 回滚位置
- 路由侧：`/root/bak-fix-20261027/`（nikki 配置 + profile + 运行时）、`/root/bak-dsh-20261027/`
- 仓库侧：`02-主路由-AN7581-QWRT/备份/`（qwrt-ct、round3-baseline/final、attic）、`04-代理-nikki/备份/`
- 历史旧件全部在 `D:\AI\_路由旧归档-20261027\`（含旧 AGENTS.md 全文、旧归档、重复备份）

### 8.4 重启 / 重拨后检查清单
1. `pidof mihomo` 只有一个 PID
2. `tr '\0' '\n' < /proc/$(pidof mihomo)/environ | grep GOMEMLIMIT` → 空
3. `uci show firewall | grep offload` → **`0` 和 `0`**；`nft list table inet fw4 | grep -c flowtable` → **`0`**
4. LuCI → 服务 → Nikki → 点保存不报错
5. `nslookup tablet.lan` → 192.168.31.122
6. 代理：外网首页能开；直连：多源测速 ≥ 850Mbps
7. `pidof nginx` 非空 且 `netstat -lntp | grep 3081` 有监听；`nft list chain inet fw4 dstnat_wan | grep -E 'dport (3081|3082)'` 应为空；本机 `curl -k --http2 https://dsh.290490.xyz:3081/` → **200 且 ALPN=h2**（外网用 VPS 复测）
8. `cat /var/log/ddns/dsh_ipv6.log | tail -5` 无 `WITH ERROR`；`cat /etc/dsh-ddns-last` == `ip -6 addr show pppoe-wan` 的地址
9. CF 链路：`ls /etc/cf/{sub.txt,cf_v4_ranges.txt} /usr/local/bin/cf-refresh.sh` 都在；`DRY=1 FORCE=1 sh /usr/local/bin/cf-refresh.sh` 打出 `DRY ok nodes=N`
10. PC 侧：`Resolve-DnsName dsh.290490.xyz -Type AAAA` 的地址 == `ip -6 addr show pppoe-wan`，且 PC 上无重拨前的旧前缀（否则 `curl -6 https://dsh.290490.xyz:3081/` 超时）
11. 代理语义（2026-11-06 起）：`yq -M '.rules | length' /etc/nikki/run/config.yaml` → **74**；组数 21（`grep -c '^  - name: "'` 为 23，含 2 个自建 proxy）；`grep -n 'NETWORK,UDP.*443' ` 应看到 **4 个 NOT** 的 v3 规则
12. DNS/IPv6：PC `Resolve-DnsName www.google.com -Type AAAA -Server 192.168.31.1` → **NODATA**；`dsh.290490.xyz AAAA` → 真实 IPv6；`www.qq.com AAAA` → 真实 IPv6；`www.google.com A` → `198.18.x`
13. sniffer：`yq -M '.sniffer' /etc/nikki/run/config.yaml` → `force-dns-mapping: false`、`parse-pure-ip: true`、HTTP/TLS `override-destination: false`、**无 QUIC 段**；`nft list table inet nikki | grep -c 'tproxy to'` → **2**
14. TUN 关闭：`uci get nikki.mixin.tun_enabled` → **0**；`yq -M '.tun.enable' /etc/nikki/run/config.yaml` → **false**；`ip link show nikki` → 报错（设备不存在）
15. 审阅收尾项（2026-11-03 晚）：`yq -M '.dns.nameserver-policy | keys'` → `+.lan`/`rule-set:oc-cn-domain`/**`rule-set:zdcn`**/`geosite:private`（**无 google-cn**）；`grep -c 'RULE-SET,zdcn,real-ip' /etc/nikki/run/config.yaml` → **1**；`vipapi.tradepower.net` A → 真实 CN IP（非 `198.18.x`）；`yq -M '.proxy-groups[] | select(.name=="♻️ 香港自动") | .use'` → 含 `CF优选`（成员 20）
16. 明文服务/陈旧规则：`netstat -lntup | grep -cE ':(21|23|139|445) '` → **0**；`nft list chain inet fw4 dstnat_wan | grep -c dnat` → **0**；`nft list chain inet fw4 input_wan | grep -c 1194` → **0**
17. 外网入口：`curl -s -H "Authorization: Bearer <secret>" "http://127.0.0.1:9090/dns/query?name=dsh.290490.xyz&type=AAAA"` 的 IP == `ip -6 addr show pppoe-wan`；不一致时 `/usr/bin/dsh-dns-guard.sh` 会自愈（日志 `/var/log/dsh-dns-guard.log`）

### 8.5 常用查询
```sh
nft list table inet fw4 | grep -c flowtable          # ★ 必须 0（7.3 起任何 flowtable 都掉到 600M）
nft get element inet nikki china_ip '{ <ip> }'       # 判 CN 归属
grep -c "\[OFFLOAD\]" /proc/net/nf_conntrack         # 软件卸载是否在跑
ip -s link show br-lan ; tc -s qdisc show dev pppoe-wan
logread -e nikki | tail -20
```

### 8.6 用浏览器做 LuCI 可视化核对（2026-11-03 起可用）

本机 **ego-browser 已可用**（v2.2.0，LuCI 登录会话保持）。PowerShell 下必须走 `.mjs` 文件形式（`-e` 只放纯 ASCII 的一行 import）：

```powershell
ego-browser nodejs -e "await import('file:///C:/Users/29049/ego/<任务目录>/round-01.mjs')"
```

- 任务目录命名 `<目标>-<日期时间>`；每轮写新的 `round-NN.mjs`；同一目标复用同一个 TaskSpace id。
- 路由后台 `http://192.168.31.1/cgi-bin/luci/` 已登录（root）；Nikki 页签：`插件配置`/`配置文件`/`混入配置`/`代理配置`/`编辑器`/`日志`。
- 2026-11-03 核对结论（LuCI 显示 = 运行时）：代理配置 `TCP=Redirect`、`UDP=TPROXY`、`IPv6 代理=未勾选`；混入配置 `TUN 启用=禁用`、`DNS 模式=Fake-IP`、`Fake-IP 范围=198.18.0.1/16`、`Fake-IP6 范围=空`、`嗅探 Redir-Host=禁用 / 纯 IP=启用 / QUIC=禁用`、`规则/GeoX 覆盖=关`；截图归档 `04-代理-nikki/备份/nikki-opt-20261103/luci/`。
- 提醒：LuCI 页面**只看不保存**（保存会写入表单值并删掉"不修改"的手工 uci 项）。

---

## 9. 历史与「不要再试」

| 项 | 结论 |
|---|---|
| **daed**（2026-09 前代理栈） | 已废弃，配置仅归档。改配置只能走 GraphQL 的坑不要再踩 |
| **ssr-plus / Passwall / passwall2** | 已卸载或不可用（2026-09 passwall2 实测代理仅 57Mbps，且 china/trust 上游必被污染） |
| **OpenClash** | 已迁 nikki；仓库只留 `openclash-20261022.yaml` 作 profile 基线参考 |
| **CF 优选轮换**（cfhk） | 已整体拆除（Worker 读取不稳定，假活）；脚本已归档 |
| **多拨（同一账号双 PPPoE）** | ★ 不支持：2026-10-29 实测第二个会话被 BRAS 拒绝，`Remote message: 21;User(...) Checking LM, (online count=1)>=(Max num=1)., Request Deny by cnc-sh.net` ⇒ `Max num=1`。要叠加上行只能换套餐/上行提速包，或多账号（需联通开通） |
| **任何 flow offload（软件/硬件）** | ★ 内核 7.3 起永远设为「无」（`0`/`0`）；开了只有 ~600M（§7-1） |
| **samba36-server**（R26.10.29 自带） | 不用 SMB，已 `disable` + `stop`；别在 LuCI 开「网络共享」 |
| **PC 侧 IPv6 旧前缀** | 重拨后旧 /64 残留会让访问 dsh / 公网 IPv6 超时，删地址或重连网卡 |
| **zram / swap** | 本固件不支持，不要再试 |
| **手改 `wan.mtu=1492`** | 会二次扣减成 1484，禁止 |
| **LibWrt 时代结论** | 旧机（IPQ60xx/daed）的 NSS/ECM/IRQ 结论与现网无关，别套用 |
| **境外 DoH/DoT 当 `nameserver`** | ★ 2026-11-03 起禁用：`respect-rules:false` 后 DNS 直连，境外 DoH 会被污染/超时；要过代理只能 `#组名` 定点（本项目不需要） |
| **给 UDP 改 TUN**（理由"内核无 nft_tproxy"） | ★ 前提是错的：`/lib/modules/7.3.1/nft_tproxy.ko` 存在、nft 里 `tproxy to :7892` 正常；TUN 走用户态 gvisor 更费 CPU。UDP 保持 **tproxy** |
| **IPv6 代理关闭时保留 `fake-ip-range6`** | ★ 会下发 `2001:2::x` 假 IPv6 却不代理 ⇒ 双栈设备 IPv6 黑洞；二者必须成对（见 §7「其他常备事实」） |
| **旧 AGENTS.md 160KB 全文** | 已归档 `_路由旧归档-20261027\AGENTS-旧版-160KB-20261027.md`，作历史查证用 |

---

## 10. 目录导航

| 路径 | 内容 |
|---|---|
| `AGENTS.md` | 本文件：环境 + 指引（唯一事实源） |
| `凭据.md` | 所有账号/密码/面板入口（敏感） |
| `ssh_run.py` | 路由器 SSH 执行工具（内置 root 密码） |
| `01-光猫-HG5585F/` | 光猫：刷机流程、**原厂 NAND 全分区备份（CU+CT，唯一副本）**、固件物料、身份数据、串口日志；**`逆向-固件R26.10.29/`（现役 QWRT 固件逆向关键件：mtwifi 守护/mt_dbdc.sh/l1profile/PPE 模块 + 索引 README——k/v 映射链与 600M 模块级证据，详见 `reports/QWRT固件逆向-R26.10.29-20261031.md`）** |
| `02-主路由-AN7581-QWRT/` | QWRT 镜像、固件分析与改造脚本、IRQ/PON 审计报告、配置备份；**`源码/lede-hg5585f/`（2026-11-01 新立：基于 coolsnowwolf/lede 的 HG5585F 自进化固件库本地副本，GitHub `Bernardxu123/lede-hg5585f`，分支模型 master=上游镜像/hg5585f=overlay 默认分支，Edge/Stable 双层发布，honk 唯一代理 + 六重熔断 + 包瘦身；现网 CT 在 CU 借纤 72h 验收前严禁刷写，见 `reports/lede-hg5585f-立项方案-20261101.md` 与 `reports/lede-hg5585f-Phase0验证报告-20261101.md`）** |
| `03-小米AP-BE6500Pro/` | 无线信道规划审计、WiFi 实测报告；**`逆向-mesh/`（小米 Mesh 协议逆向资料库：mesh 栈原件 14 件、Ghidra 反编译 C×3、一页式索引 README——auth 密钥/线格式/calcbssid 等结论 + 工具链复刻手册 + 固件包格式坑位；入口 `逆向-mesh/README.md`，结论详见 `reports/小米Mesh协议逆向-20261031.md`）** |
| `04-代理-nikki/` | 当前 profile（与线上同 sha）、daed 时代规则快照、DSH Pocket 部署件；**`备份/nikki-opt-20261103/`：profile-before/after/final、run-config-{before,final,stage2-test}、uci-nikki-{before,after-luci-save,final}.conf、luci-mixin.js、luci-nikki-rpc.ucode、state-before/after.txt** |
| `05-网络测绘-netplan/` | 家用 WiFi 测绘工具（survey/index.html） |
| `06-CF优选/` | **CF 订阅优选流水线**：`cfopt.py`（电脑侧抓池/三段探测/colo/emit/upload/verify）、`router/cf-refresh.sh`、`deploy_router.py`、`tests/`、`data/`（产物）、`state/`（上传快照，不入库）。见 §4.6 |
| `reports/` | 当前技术栈的过程报告（按时间；**2026-11-03 新增 `路由器LuCI全面检查-20261103.md`（Web 后台逐页检查+清理+截图）、`代理栈-QUIC-DNS-sniffer优化-20261103.md`（细节+证据+第二阶段 reconciliation）与 `代理栈优化-总结-20261103.md`（自包含总览，专供外部 AI 审阅）**；2026-10-31 新增：`小米Mesh协议逆向`、`主路由-小米AP协同执行报告`、`执行计划-主路由k-v对齐`——k/v 已按执行计划于 10-31 落地生效，判据 `/tmp/profiles/dbdc.b?.dat` RRMEnable/WNMBTMEnable=1；`QWRT固件逆向-R26.10.29`——现役固件全量解包，补齐 k/v 映射链（mtwifi 守护）与 600M 模块级证据） |
| `tools/` | 分析/运维脚本：**`dsh-dns-guard.sh`（路由器侧 mihomo DNS 映射守护，cron */15）、`socks5_udp_probe.py`（SOCKS5 UDP ASSOCIATE 探测节点 UDP 中继）、`quic_udp_matrix.py`（跨节点 UDP 矩阵+选择恢复）、`patch_profile_review_20261103.py`（外部审阅收尾补丁：zdcn real-ip/policy、删 google-cn policy、provider 600s、CF 回归香港自动，幂等+锚点断言）、`patch_profile_20261103.py`（QUIC/DNS/sniffer/去重/删 fake-ip-range6 的幂等补丁，带锚点断言）、`deploy_nikki_opt_20261103.sh`（预校验+备份+回滚的部署脚本）、`update_agents_20261103.py`（本次文档更新）**、`fit_analyze.py`（拆固件 FIT）、`rootfs_diff.py`、`textdiff.py`、`xwrt_compare.py`、`xwrt_dtb.py`、`apply_subs.py`（追加机场 provider）、`tune_profile.py`（注释/摘除 provider、改组 exclude-filter）、`restore_cf_after_flash.py`（**刷机后重建 CF 链路**）、`wan_speedtest.py`（多源聚合测速）、`fix_tradepower_direct.py`（先期把 MatchBest API 规则硬编码进 profile）、`move_tradepower_to_list.py`（最终把该规则搬进 zdcn 列表 + 换 CDN，见 §7-6）、**`deploy_dsh_entry.py`（DSH 入口路由器侧一键部署：nginx.conf/upstream/watchdog/DDNS 脚本 + 删 DNAT + 调 DDNS 间隔 + cron，幂等，见 §5）** |
| `plugins/` | DSH 插件（dsh-usage-stats）源码 |
