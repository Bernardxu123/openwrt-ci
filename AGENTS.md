# 家庭网络环境 · 运维手册（AI 必读）

> 最后更新：**2026-11-01 08:00**（DSH 手机端外网直连修复+提速：Pocket 端口漂移 3081→3082 导致公网 502/超时、两条 DNAT 抢流量且 Pocket 只监听 IPv4 必失败 ⇒ 删 DNAT、PC 固定 `proxyPort`、watchdog 自动发现端口；nginx 加 **HTTP/2** + `/assets/` 强缓存 + gzip + 上游 keepalive；DDNS 轮询 **5→30 分钟**（重拨/重启由 hotplug 事件驱动）+ 12h 对账；外网 VPS 实测 **HTTP/2 200 / TTFB 0.22–0.31s**，见 §5 / §7-7。此前 **2026-10-30 10:50**：MatchBest 登录事故：`vipapi.tradepower.net`（阿里云杭州）因 fake-IP + `GEOIP,CN,no-resolve` 被误送进香港机场节点、TLS 被断 ⇒ 条目归 GitHub `Bernardxu123/xu` 的 `zdcn.list`（`RULE-SET,zdcn → 🎯 直连`）、profile 不硬编码，固件侧只把 zdcn 的 CDN 换成可 purge 的 `cdn.jsdelivr.net`；已实测登录成功，见 §7-6。此前 **2026-10-29 21:40**（配置审查：`GEOSITE,google-cn` 提前到 `GEOSITE,google` 之前并加 real-ip/CN DNS 直连；乌龟 403 为后台订阅开关默认关闭的预期态、UA 改动已回退；此前删除 `♻️ CF自动` / `🇨🇫 CF节点` 两个独立分组，`CF优选` 并入 `♻️ 香港自动` / `🇭🇰 香港节点` / `🌐 全部节点`；刷入 **QWRT R26.10.29 / 内核 7.3**：★★ **offload 铁律反转——必须设为「无」（`flow_offloading=0` + `hw=0`），软件卸载与硬件卸载都只有 ~600M**；samba/ipv6set 回到镜像（samba 已 disable）；刷机后 **nginx 包 + CF 优选链路**需要恢复（§5 / §4.6）；PC 侧 IPv6 旧前缀要清理。2026-10-28：新增订阅 **吹雪 / 顺畅**、极速注释、**CF 优选流水线上线**；2026-10-27 全面整理 + 文档重写）
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
- 固件 **QWRT R26.10.29**（底层 OpenWrt **25.12.3** / `r8073-f79e49921a`），内核 **`7.3`**（2026-10-29 从 `5.4.302` 大版本跳升，235 个 kmod 全量重建；`uname -a` 为 `7.3 #0 SMP PREEMPT`），`aarch64`
- SoC **Airoha AN7581**，4×Cortex-A53，RAM **412604 kB（≈403MB）**，**无 swap**（overlay 是 ubifs，不支持 swapfile）
- 已有模块：`nf_flow_table{,_hw,_inet}`、`an7581_bsp_ppe`（依赖 `br_netfilter` + `nf_flow_table_inet`，并替换 `nf_flow_offload_{ip,inet}_hook`）、`nft_tproxy`、`xt_TPROXY`
- 其它版本事实（R26.10.29）：`luci-mod-network 26.300.70979`、`mihomo` 镜像内 `1.19.32`（由 nikki 自动更新，以 `mihomo -v` 为准）、`samba36-server` / `luci-app-ipv6set` **重新进镜像**（samba 已 `disable`）

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
判据：`nft list table inet fw4 | grep -c flowtable` **必须是 0**，`grep -c "\[OFFLOAD\]" /proc/net/nf_conntrack` 也应为 0。

> **历史（5.4.302 / R26.10.25-26）**：软件 914M、硬件 640M、全关 845M —— 与 7.3 结论**相反**，别套用。
> 原因（推断；证据：`an7581_bsp_ppe.ko` 依赖 `nf_flow_table,br_netfilter,nf_flow_table_inet`、替换了 `nf_flow_offload_{ip,inet}_hook`，且模块内无任何 pppoe 符号）：7.3 上 PPE 会接管 flowtable 条目但不会补 PPPoE 头 ⇒ 只要存在 flowtable，PPPoE 流就被拖进半残快路径。

### 3.4 sysctl / 队列（已在目标状态，勿动）
`tcp_congestion_control=bbr`、`default_qdisc=fq_codel`、`tcp_mtu_probing=1`、`netdev_max_backlog=4096`、`rmem_max=wmem_max=1048576`。

### 3.5 持久化与定时任务
`/etc/sysupgrade.conf` 保留：`/etc/nikki/`、`/etc/dsh-nginx/`、`/etc/init.d/dsh-nginx`、`/usr/bin/dsh-watchdog.sh`、`/etc/acme.sh/`、`/etc/dsh-nginx/cert/`、`/etc/crontabs/root`、`/etc/sysctl.d/`、`/etc/cf-dns.token`、`/etc/dsh-ddns-last`、`/etc/dsh-cf-{zone,record}.id`、`/etc/init.d/pon-macclone`、`/usr/lib/ddns/update_cloudflare_dsh.sh`、`/etc/cf/`、`/usr/local/bin/cf-refresh.sh`（后两项 2026-10-29 才补进 keep；之前刷机会把 CF 链路整条丢掉）。

cron 共 7 条（2026-11-01 实测）：acme 续期（`17 3 * * *`）、nikki 日志清理（`*/5`）、nginx `check_ssl`（`3 3 12 12 *`）、**`*/5 * * * * /usr/bin/dsh-watchdog.sh`（DSH 入口/DDNS 看门狗；2026-11-01 从 `*/2` 降到 `*/5`，轻量化）**、**`17 4 * * * /usr/local/bin/cf-refresh.sh`（CF 优选刷新，40h 门控 → 实际 40–56h 一轮，见 §4.6）**、`0 2 * * *`（清 `msd_lite` 日志）、`0 4 * * * /etc/coremark.sh`。

> ⚠️ `/etc/config/nikki` 与 profile 都在 `/etc/nikki/` 下，升级保留；但 **`/www/luci-static/resources/view/nikki/app.js` 不在 keep 里**，重刷固件后 LuCI 页面会回到原版（见 §7-2）。

---

## 4. 代理栈：nikki + mihomo

### 4.1 组件与端口

| 项 | 值 |
|---|---|
| nikki | `2026.10.10-1`，`luci-app-nikki 1.26.2-r1` |
| mihomo | `v1.19.32` linux/arm64（go1.27.1），`/usr/bin/mihomo → /usr/libexec/mihomo` |
| 数据面 | **TCP = redirect(7891)**、**UDP = tproxy(7892)**；TUN 设备 `nikki` 存在但实测只有个位数包（**不在主路径**） |
| DNS | mihomo 监听 `[::]:1053`；LAN 的 `:53` 被 nft **劫持到 1053** |
| 面板 | `[::]:9090`，`allow_lan=1`，secret 见 `凭据.md`（**6 位，偏弱**） |
| 配置 | uci `nikki.config.profile='file:openclash-20261022.yaml'` |
| | 源文件 `/etc/nikki/profiles/openclash-20261022.yaml`（15.2KB / 519 行）→ 运行时 `/etc/nikki/run/config.yaml` |
| 订阅源 | `proxy-providers` **订阅源生效 3 个**：`乌龟`、`吹雪`、`顺畅`（后两个 2026-10-28 新增）；另有 **file provider `CF优选`**（`/etc/nikki/run/providers/cf-optimized.yaml`，§4.6）；**`乌龟` 需在网站后台开启「订阅」开关才会订阅（默认关），403 属预期；它保留缓存节点、节点故障时再更新，不要加 UA header（2026-10-29 已回退）**；`极速` **已注释**（2026-10-28 流量用尽，provider 块和 5 处 `use:` 条目都带 `#`，**恢复时两处一起去 `#`**，只去一处会导致配置校验失败）→ 缓存 `/etc/nikki/run/providers/proxy/{wugui,chuixue,shunchang}.yaml`（`jisu.yaml` 旧缓存仍留在盘上但不加载），节点自动加前缀 `[名] `，`interval: 86400` 由 mihomo 自己刷新（**没有 cron 依赖**） |

### 4.2 内核级「绕过大陆」（最省性能的一层）
- `nikki.proxy.bypass_china_mainland_ip=1`、`nikki.proxy.bypass_china_mainland_ip6`
- nft 表 `inet nikki` 的 `dstnat` / `mangle_prerouting_lan` / `nat_output` 里，`ip daddr @china_ip counter return` **排在所有 redirect 之前** ⇒ 命中即回内核直连，**根本不进 mihomo**
- `@china_ip` = **7362** 段、`@china_ip6` = **1655** 段，来自 `/etc/nikki/nftables/geoip{6}_cn.nft`（**包自带静态文件，无自动更新任务**）
- 判 CN 归属必须查集合，不能看域名：
  ```sh
  nft get element inet nikki china_ip '{ 140.207.247.169 }'
  ```

### 4.3 DNS 架构（三层，别搞混）

| 层 | 行为 |
|---|---|
| LAN 客户端查 `:53` | 被 nft `lan_dns_hijack` 直接 redirect 到 `mihomo:1053`（**dnsmasq 被绕过**） |
| mihomo DNS | fake-ip `198.18.0.1/16` + `2001:2::1/64`；`fake-ip-filter` 用 rule 模式：`RULE-SET,oc-cn-domain → real-ip`、`GEOSITE,private → real-ip`、`GEOSITE,google-cn → real-ip`（2026-10-29 加，配合 `nameserver-policy` 的 `geosite:google-cn → 223.5.5.5/119.29.29.29`）、`*.lan/*.local → real-ip`、其余 `MATCH → fake-ip` |
| 上游 | 国内 `nameserver-policy`：`rule-set:oc-cn-domain` + `geosite:private` → `223.5.5.5 / 119.29.29.29`；**`+.lan` → `192.168.31.1`（dnsmasq，出内网真实 IP）**；国外 DoH `https://1.1.1.1/dns-query` + `https://dns.google/dns-query`（`respect-rules: true`，经代理） |

### 4.4 规则表（61 条，自上而下首个命中）
顺序要点（**改规则前必须确认前面没有更早规则吃掉流量**）：
1. `GEOSITE,private` + 一堆保留网段 `IP-CIDR` → 🎯 直连
2. STUN/游戏 UDP（3478/19302/7844）、NTP(123) → 直连
3. `AND((NETWORK,UDP),(DST-PORT,443),(NOT(GEOIP,CN)))` → **REJECT**（禁境外 QUIC）
4. 自有服务：`vlook/pc.290490.xyz` → 默认代理；`xx/dsh.290490.xyz` 与 `*.290490.xyz` → 直连
   + **`tradepower.net`（MatchBest 后台 API，阿里云杭州 39.99.205.168）走 `RULE-SET,zdcn` 直连**（2026-10-30；条目写在 GitHub `Bernardxu123/xu` 的 `zdcn.list` 里，profile 不硬编码，原因见 §7-6）
5. `googleapis.cn` → 直连；`speedtest.cn` → ✈️ Speedtest(=DIRECT)
6. `RULE-SET,zdcn` → 直连；`RULE-SET,zdgw` → 默认代理
7. Steam 内容/Cdn 直连，`GEOSITE,steam` → 默认代理
8. AI 固定出口（**必须排在 `GEOSITE,google` 之前**）：`aistudio/makersuite/alkalimakersuite*/generativelanguage` + `GEOSITE,google-gemini` → 🛡️ 稳定固定
9. `GEOSITE,youtube` → 📺 YouTube；`opencode.ai` → 🤖 ChatGPT；`GEOSITE,category-ai-!cn` → 🤖 ChatGPT
10. 流媒体（netflix/disney/spotify/tiktok）、GitHub、Telegram、Twitter、Google、**`GEOSITE,google-cn → 🎯 直连`（必须排在 `GEOSITE,google` 之前；2026-10-29 修正，否则 112 个 google-cn 域名全被 GOOGLE 规则吃掉）**、Apple、OneDrive、Microsoft、Oracle、Ookla
11. `RULE-SET,oc-cn-domain → 直连` → `GEOIP,CN → 直连` → `MATCH → 🐟 漏网之鱼`

### 4.5 分组与出口
`🚀 默认代理`（→ ♻️ 香港自动 → 组内最优 HK，实测常见 `[顺畅] 🇨🇳香港原生htk高速` / `[吹雪] 🇭🇰香港•移联02`）、`🛡️ 稳定固定`（→ `🇸🇬 新加坡-自建TLS`）、`♻️ 香港自动`、`🎯 直连`、`🐟 漏网之鱼`、`✈️ Speedtest`(DIRECT)、`📺 YouTube`、`🎬 流媒体`、`🤖 ChatGPT`、`📦 GitHub`、`🔍 Google`、`🪟 微软`、`🍎 Apple`、`🏢 甲骨文 Oracle`、`✈️ Telegram`。

节点来源：5 个组用 `use:` 引用**当前生效的 3 个 provider**（`乌龟`/`吹雪`/`顺畅`；`极速` 已注释），其中 `♻️ 香港自动` / `🇭🇰 香港节点` / `🌐 全部节点` **额外引用 `CF优选`**（2026-10-29：原 `♻️ CF自动` / `🇨🇫 CF节点` 两个独立分组已删除，CF 节点只作备用并入，不再单列组）——`♻️ 香港自动`/`♻️ 新加坡自动` 是 url-test（gstatic 测速，600s/容差 100），`🇭🇰 香港节点`/`🇸🇬 新加坡节点`/`🌐 全部节点` 是 select；组内节点名形如 `[吹雪] 🇭🇰香港•移联01`，靠 filter `港|hk|hong ?kong` / `新加坡|狮|singapore|sg-?[0-9]` 归组，`exclude-filter` 剔除「剩余流量/套餐到期」这类信息节点。**`♻️ 香港自动` 额外排除 `家宽`**（2026-10-28：顺畅家宽节点延迟很低 37–56ms 但实测吞吐偏慢）；注意 exclude-filter 是**逐组**字段，其余组仍能看到家宽节点。**新增机场只动 provider + 5 处 `use:`，不要建平行新组**（2026-10-28 吹雪/顺畅即按此办理）。

### 4.6 CF 订阅优选流水线（2026-10-28 上线）

- **目标**：Worker 订阅只做"换入口 IP"，所以优选判据是"这个 IP 能不能承载 `SNI=goui.290490.xyz`"，不是"IP 快"。
- **电脑侧**（`06-CF优选/cfopt.py`，手动，单轮约 1 分钟）：`ranges`（CF 官方 15 条 v4 网段，7 天缓存）→ `pool`（9 源并发，≥2 源成功才继续，非 CF 段直接拒）→ `probe`（TCP → **TLS SNI+证书校验** → **WS 升级 101/200**，A/B/C 三段）→ `colos`（取真实 colo 打标签）→ `emit`（`yx.txt` / `mihomo_proxies.yaml`）→ `upload`（写 Worker KV `yx`，回读校验）→ `verify`（线上订阅 `ALL_IN_CF=1`）。
- ★ **探测必须临时旁路**：本机流量被 `dstnat` 透明代理，直连探测才有意义。脚本在 `inet nikki dstnat` 顶部插 `ip saddr 192.168.31.218 tcp dport 443 return`（注释 `cfopt-probe-bypass`），结束/异常都会删；判据是"到 CF 边缘 TCP RTT ≥4ms"（旁路生效时 240–290ms，未生效 1.5ms）。
- **路由器侧**（`/usr/local/bin/cf-refresh.sh`，cron 04:17，40h 门控）：`curl` 面板订阅 → awk 校验（节点数 ≥5、每个 `server` 命中 `/etc/cf/cf_v4_ranges.txt`、`servername` 全对、无 `ech:`）→ 写 `.new` 再 `mv`（原子）→ `PUT /providers/proxies/CF优选` 重载（`reloaded=api:204`，无中断；失败退回 `/etc/init.d/nikki reload`）。实测 1–2s，内存 +1MB，无 OOM。
- **接线**：profile 里 `CF优选`（`type: file`，`path: /etc/nikki/run/providers/cf-optimized.yaml`）已并入 `♻️ 香港自动`（url-test）/`🇭🇰 香港节点`（select）/`🌐 全部节点`（select）；**2026-10-29 已删除原 `♻️ CF自动` / `🇨🇫 CF节点` 两个独立分组**（用户要求，`🚀 默认代理` 不再单列 CF 组）。节点名 `[CF] HK-n`。
- ★ **file provider 的 path 必须在 `/etc/nikki/run` 下**：放 `/etc/nikki/providers/` 会报 `path is not subpath of home directory or SAFE_PATHS ... allowed paths: [/etc/nikki/run]`，core 直接起不来（`active with no instances`）。
- **标签规则**：colo 命中 `SIN` → `SG-n`，其余一律 `HK-n`。实测本机到 CF 的落点是 **HKG / SJC / LAX（150 个抽样里 0 个 SIN）**，所以全标 HK；CF 组定位**备用**（实测 8 Mbps / RTT 240–600ms），主力仍是机场。
- 回滚：`/root/bak-cfopt-20261028-152430/`（profile+cron+uci）；上传侧 `cfopt.py upload --rollback`（用 `state/yx.prev.txt`）；停自动刷新删 cron 那行即可。

---

## 5. DSH 手机端远程入口

- 地址：`https://dsh.290490.xyz:3081`（Cloudflare 上 `dsh` 的 AAAA 为 **DNS-only**，指向 `pppoe-wan` 的公网 IPv6）
- 路由侧：`/etc/dsh-nginx/` 独立 procd（nginx `[::]:3081` TLS + **Host 强制改写** + **HTTP/2**）→ 反代 PC `192.168.31.218:<实际端口>` 的 DSH Pocket；上游写在 `/etc/dsh-nginx/upstream.conf`，由看门狗维护
- 证书：`acme.sh`（Let's Encrypt **DNS-01**，Cloudflare，token `/etc/cf-dns.token`）→ `/etc/dsh-nginx/cert/`
- DDNS：`ddns.dsh_ipv6` + `/usr/lib/ddns/update_cloudflare_dsh.sh`（**每 30 分钟**轮询 + `95-ddns` 在 ifup 时立即触发；IP 只在重拨/重启变，2026-11-01 从 5 分钟降频；另每 12 小时对账一次线上记录）
- 防火墙：`Allow-DSH-Pocket-IPv6`（wan→tcp/3081 ACCEPT，仅 IPv6）
- **为什么必须走 nginx**：DSH Pocket 的 `classifyHost()` 把裸 IPv6 Host 当 loopback 免密；nginx 改写 Host 后，IP 直连也只能看到 PIN 页
- ★ **Pocket 端口会漂（2026-11-01 事故）**：DSH Pocket 默认 3081，启动时被占会 `+1..+9`；当天 DSH 16:11 重启后落到 **3082**，nginx 仍指 3081 ⇒ 本机 8 秒后 502；同时有两条未记录的 DNAT（wan 3081/3082 → PC 的 IPv6）抢在 nginx 前把流量劫到 PC，而 Pocket 只监听 `0.0.0.0`（IPv4）⇒ 外网一律超时。**已删 DNAT**；PC 侧 `settings.json` 写入 `"proxyPort": 3081`（下次 DSH 重启生效）；路由器看门狗每 5 分钟探测，**只探当前端口，探不通才扫 3081–3084（扫描 10 分钟节流）**，漂移时自动改写 upstream 并 reload
- ★ **不要再给 3081/3082 加 DNAT**：会绕过 TLS/Host 改写，而且 PC 的 IPv6 是 RA/SLAAC，前缀一换就失效
- ★ **nginx 性能/稳定性（2026-11-01 实测）**：`http2 on`（ALPN=h2，外网 VPS TTFB 0.22–0.31s）、`/assets/` 一年 immutable 缓存、gzip（HTML 42670→2074 B）、上游 keepalive、`proxy_connect_timeout 2s`、删掉已下线的 `.222` 备份（故障时曾多等 5 秒）
- ★ **nginx 启动依赖 `/var/lib/nginx`（tmpfs，重启即丢）**：独立 init 的 `start_service()` 必须先 `mkdir -p /var/lib/nginx/{body,proxy,fastcgi,uwsgi,scgi}`，否则重启后 nginx 报 `mkdir() "/var/lib/nginx/body" failed` 直接退出 ⇒ 3081 无监听（2026-10-27 事故：DDNS 正常但入口打不开，被误判成 DDNS 失效）
- ★ **看门狗**：`/usr/bin/dsh-watchdog.sh` + cron `*/5 * * * *`（2026-11-01 从 `*/2` 降频）—— nginx 不在就 `restart`；`dynamic_dns_updater` 不在就后台拉起（`-S <section> -- start` 是前台常驻，**必须加 `&` 放后台**，否则 cron 卡死）；端口自动发现；`pppoe-wan` 的 IPv6 与 `/etc/dsh-ddns-last` 持续 15 分钟不一致 → 告警并重启 ddns；证书 <14 天告警（每小时）；单实例锁防重叠；**端口变更 reload 后做一次本地 HTTPS 探针（`Host: dsh.290490.xyz` → `[::1]:3081`），非 200/302 则自动 `restart`**（2026-11-01 实测 OpenSSL 偶发 `SSL_CTX_new` emerg 会让 reload 静默失效、旧 worker 继续用旧上游）
- ★ **DDNS 重拨存活**：`ddns.dsh_ipv6.retry_max_count=0`（无限重试）。原值 3 会在重拨瞬间 `pppoe-wan` 无地址时连续失败 3 次后自杀，只等 hotplug ifup 捞回（不保证）
- ★ **刷机后恢复（2026-10-29 于 R26.10.29 实测）**：sysupgrade 只保 keep 内的 `/etc` 文件与 `/etc/nikki`。三件事：
  1. **nginx-ssl / libpcre2 / libxml2-16 包会丢**（`/usr/sbin/nginx` 不存在 ⇒ 3081 无监听）→ `sh /usr/bin/dsh-restore.sh`（幂等；实测装回 `nginx-ssl 1.26.3` 后 3081 立即 200）
  2. **CF 优选链路整条丢**（`/etc/cf/` 与 `/usr/local/bin/cf-refresh.sh` 原不在 keep，但 cron 那行还在 → 每天 04:17 静默失败）→ 已补进 keep；PC 侧 `python tools/restore_cf_after_flash.py` 一键重建并 `DRY` 自检（期望 `DRY ok nodes=N`）
  3. **PC 侧 IPv6 旧前缀残留**（重拨后旧 /64 失效）会让 `curl -6 https://dsh...` 超时/`000`，删掉旧地址或重连网卡即可（判据：PC 能 ping 通 `ip -6 addr show pppoe-wan` 的地址）

---

## 6. 性能基线与测量方法

**当前基线（内核 7.3 / R26.10.29，offload=「无」）**
- 用户侧实测口径：**offload 必须设为「无」才满速；软件卸载、硬件卸载都只有 ~600M**（判据见 §7-1）。
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

### ★4 境外 DoT 会失败并引发健康检查风暴
`tls://8.8.4.4:853` 经 `🐟 漏网之鱼 → 🚀 默认代理 → ♻️ 香港自动` 反复失败（core.log 120+ warning，还会把 `香港自动` 判 failed 触发 re-test）。已换成 `https://dns.google/dns-query`。

### ★5 fake-ip 例外判据
要加 `real-ip` 例外，**先证"真实 IP ∈ `@china_ip`"**，否则零收益。反例：`cn.download.nvidia.com` 真实 IP 是 Akamai `2.22.242.x`（不在 CN 段），强推直连只会更慢；`www.nvidia.cn` 才是国内 IP（内核已直连）。

### ★6 fake-IP + `GEOIP,CN,...,no-resolve` ⇒ 国内站点被误送进代理（2026-10-30 MatchBest 登录事故）
- **现象**：`https://app.matchbest.co` 页面能正常打开，但点「登录」必失败；浏览器网络面板里 `POST https://vipapi.tradepower.net/v1/account/login_sp` = **`net::ERR_CONNECTION_CLOSED`**，路由器上 curl 同一 URL 报 `TLS alert, decode error` / `unexpected eof while reading`
- **原因链**：`vipapi.tradepower.net` 真实 IP **39.99.205.168**（阿里云杭州，属 `@china_ip` 的 `39.98.0.0/15`）；但 LAN 客户端拿到的是 fake-IP（`198.18.7.216`），而规则 `GEOIP,CN,🎯 直连,no-resolve` **带 `no-resolve` 就不会为域名去解析**，fake-IP 当然不属 CN ⇒ 落到 `MATCH,🐟 漏网之鱼` ⇒ 香港机场节点去连国内 API，TLS 被直接掐断
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

### 其他常备事实
- 现固件**有** `nft_tproxy`（UDP tproxy 在用）；**仍无 zram，仍不能 swap**（ubifs）
- MTU：`wan.mtu` 保持 1500，协商 1492；不要填 1492
- 9090 面板 secret 6 位且 `allow_lan=1`，属**待加固项**
- 不要手改 `/etc/nikki/mixin.yaml`（ucode 会覆盖），用 `uci set nikki.mixin.*`
- sniffer 生效需要 `mixin.sniffer=1` **且** `mixin.sniffer_sniff=1`
- IRQ 全落 CPU0，但饱和时 CPU 仅 29% ⇒ **不需要动 IRQ/RPS**
- `bypass_china_mainland_ip`（内核 nft）与 profile 里的 `GEOIP,CN` 规则是**两套机制**；前者命中后规则表根本看不到这些流量

---

## 8. 运维手册

### 8.1 连路由器
```powershell
python ssh_run.py 'uci show firewall | grep offload'          # 单引号包远程命令
python ssh_run.py 'cmd1' 'cmd2'                                # 多条
```

### 8.2 改代理配置的标准流程
```sh
# 1 备份
cp /etc/nikki/profiles/openclash-20261022.yaml /root/bak-$(date +%m%d)/profile.yaml
# 2 改源 profile（不要改 run/config.yaml，会被重新生成）
# 3 生效
/etc/init.d/nikki restart && sleep 8
# 4 验证
/etc/init.d/nikki status; pidof mihomo
grep -cE "level=(error|fatal)" /var/log/nikki/core.log
grep -n "关键行" /etc/nikki/run/config.yaml       # 确认改动进了运行时
nslookup www.baidu.com 192.168.31.1               # 应为真实国内 IP
nslookup www.google.com 192.168.31.1              # 应为 198.18.x
```

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

### 8.5 常用查询
```sh
nft list table inet fw4 | grep -c flowtable          # ★ 必须 0（7.3 起任何 flowtable 都掉到 600M）
nft get element inet nikki china_ip '{ <ip> }'       # 判 CN 归属
grep -c "\[OFFLOAD\]" /proc/net/nf_conntrack         # 软件卸载是否在跑
ip -s link show br-lan ; tc -s qdisc show dev pppoe-wan
logread -e nikki | tail -20
```

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
| **旧 AGENTS.md 160KB 全文** | 已归档 `_路由旧归档-20261027\AGENTS-旧版-160KB-20261027.md`，作历史查证用 |

---

## 10. 目录导航

| 路径 | 内容 |
|---|---|
| `AGENTS.md` | 本文件：环境 + 指引（唯一事实源） |
| `凭据.md` | 所有账号/密码/面板入口（敏感） |
| `ssh_run.py` | 路由器 SSH 执行工具（内置 root 密码） |
| `01-光猫-HG5585F/` | 光猫：刷机流程、**原厂 NAND 全分区备份（CU+CT，唯一副本）**、固件物料、身份数据、串口日志；**`逆向-固件R26.10.29/`（现役 QWRT 固件逆向关键件：mtwifi 守护/mt_dbdc.sh/l1profile/PPE 模块 + 索引 README——k/v 映射链与 600M 模块级证据，详见 `reports/QWRT固件逆向-R26.10.29-20261031.md`）** |
| `02-主路由-AN7581-QWRT/` | QWRT 镜像、固件分析与改造脚本、IRQ/PON 审计报告、配置备份 |
| `03-小米AP-BE6500Pro/` | 无线信道规划审计、WiFi 实测报告；**`逆向-mesh/`（小米 Mesh 协议逆向资料库：mesh 栈原件 14 件、Ghidra 反编译 C×3、一页式索引 README——auth 密钥/线格式/calcbssid 等结论 + 工具链复刻手册 + 固件包格式坑位；入口 `逆向-mesh/README.md`，结论详见 `reports/小米Mesh协议逆向-20261031.md`）** |
| `04-代理-nikki/` | 当前 profile、daed 时代规则快照、DSH Pocket 部署件 |
| `05-网络测绘-netplan/` | 家用 WiFi 测绘工具（survey/index.html） |
| `06-CF优选/` | **CF 订阅优选流水线**：`cfopt.py`（电脑侧抓池/三段探测/colo/emit/upload/verify）、`router/cf-refresh.sh`、`deploy_router.py`、`tests/`、`data/`（产物）、`state/`（上传快照，不入库）。见 §4.6 |
| `reports/` | 当前技术栈的过程报告（按时间；2026-10-31 新增：`小米Mesh协议逆向`、`主路由-小米AP协同执行报告`、`执行计划-主路由k-v对齐`——k/v 已按执行计划于 10-31 落地生效，判据 `/tmp/profiles/dbdc.b?.dat` RRMEnable/WNMBTMEnable=1；`QWRT固件逆向-R26.10.29`——现役固件全量解包，补齐 k/v 映射链（mtwifi 守护）与 600M 模块级证据） |
| `tools/` | 分析/运维脚本：`fit_analyze.py`（拆固件 FIT）、`rootfs_diff.py`、`textdiff.py`、`xwrt_compare.py`、`xwrt_dtb.py`、`apply_subs.py`（追加机场 provider）、`tune_profile.py`（注释/摘除 provider、改组 exclude-filter）、`restore_cf_after_flash.py`（**刷机后重建 CF 链路**）、`wan_speedtest.py`（多源聚合测速）、`fix_tradepower_direct.py`（先期把 MatchBest API 规则硬编码进 profile）、`move_tradepower_to_list.py`（最终把该规则搬进 zdcn 列表 + 换 CDN，见 §7-6）、**`deploy_dsh_entry.py`（DSH 入口路由器侧一键部署：nginx.conf/upstream/watchdog/DDNS 脚本 + 删 DNAT + 调 DDNS 间隔 + cron，幂等，见 §5）** |
| `plugins/` | DSH 插件（dsh-usage-stats）源码 |
