# 家庭网络环境 · 运维手册（AI 必读）

> 最后更新：**2026-10-27 17:20**（全面整理 + 文档重写；同日已修：nikki 保存报错、GOMEMLIMIT 去除、内网 DNS、**硬件流量卸载导致 600M 上限**）
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

**无线**：主路由 2.4G `ch6/HE20`、5G `ch149/HE80`（**country 必须 CN**，否则 ch149 是 NO-IR）；AP 2.4G `ch1/HT40`、5G `ch36/160`。手机/平板为随机 MAC，关掉"随机 MAC"才能让租约稳定。

---

## 3. 主路由（HG5585F / QWRT）

### 3.1 版本与硬件
- 固件 **QWRT R26.10.25**（底层 OpenWrt **25.12.3**），内核 `5.4.302`，`aarch64`
- SoC **Airoha AN7581**，4×Cortex-A53，RAM **410244 kB（≈400MB）**，**无 swap**（overlay 是 ubifs，不支持 swapfile）
- 已有模块：`nf_flow_table{,_hw,_inet}`、`an7581_bsp_ppe`、`nft_tproxy`、`xt_TPROXY`

### 3.2 关键 UCI

```sh
# 网络
network.wan.proto=pppoe ; network.wan.mtu=1500        # ★ 必须 1500；pppd 会自己协商成 1492
                                                       #   切勿手动填 1492（会二次扣减成 1484）
network.wan.mru=1500
network.@device[?wan].mtu=1500                         # pon0 侧维持 1500

# ★★ 防火墙 offload（600M 事故的根因，见 §7-1）
firewall.@defaults[0].flow_offloading=1                # 软件卸载：开（更快且省 CPU）
firewall.@defaults[0].flow_offloading_hw=0             # 硬件卸载：★ 必须 0
```

### 3.3 offload 行为（实测）
```
flow_offloading_hw=0 → flowtable ft { devices = { br-lan, pon0.995, pppoe-wan } }   ← 正确
flow_offloading_hw=1 → flowtable ft { devices = { lan1..4, pon0, ra0, rai0 }  flags offload }  ← 对不上 PPPoE
```
用 `nft list table inet fw4 | grep -A5 flowtable` 复核。

### 3.4 sysctl / 队列（已在目标状态，勿动）
`tcp_congestion_control=bbr`、`default_qdisc=fq_codel`、`tcp_mtu_probing=1`、`netdev_max_backlog=4096`、`rmem_max=wmem_max=1048576`。

### 3.5 持久化与定时任务
`/etc/sysupgrade.conf` 保留：`/etc/nikki/`、`/etc/dsh-nginx/`、`/etc/init.d/dsh-nginx`、`/etc/acme.sh/`、`/etc/dsh-nginx/cert/`、`/etc/crontabs/root`、`/etc/sysctl.d/`、`/etc/cf-dns.token`、`/etc/dsh-ddns-last`、`/etc/dsh-cf-{zone,record}.id`、`/etc/init.d/pon-macclone`、`/usr/lib/ddns/update_cloudflare_dsh.sh`。

cron 只有 3 条：acme 续期（`17 3 * * *`）、nikki 日志清理（`*/5`）、nginx `check_ssl`（每年 12-12）。

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
| | 源文件 `/etc/nikki/profiles/openclash-20261022.yaml`（13.5KB）→ 运行时 `/etc/nikki/run/config.yaml` |

### 4.2 内核级「绕过大陆」（最省性能的一层）
- `nikki.proxy.bypass_china_mainland_ip=1`、`bypass_china_mainland_ip6=1`
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
| mihomo DNS | fake-ip `198.18.0.1/16` + `2001:2::1/64`；`fake-ip-filter` 用 rule 模式：`RULE-SET,oc-cn-domain → real-ip`、`GEOSITE,private → real-ip`、`*.lan/*.local → real-ip`、其余 `MATCH → fake-ip` |
| 上游 | 国内 `nameserver-policy`：`rule-set:oc-cn-domain` + `geosite:private` → `223.5.5.5 / 119.29.29.29`；**`+.lan` → `192.168.31.1`（dnsmasq，出内网真实 IP）**；国外 DoH `https://1.1.1.1/dns-query` + `https://dns.google/dns-query`（`respect-rules: true`，经代理） |

### 4.4 规则表（61 条，自上而下首个命中）
顺序要点（**改规则前必须确认前面没有更早规则吃掉流量**）：
1. `GEOSITE,private` + 一堆保留网段 `IP-CIDR` → 🎯 直连
2. STUN/游戏 UDP（3478/19302/7844）、NTP(123) → 直连
3. `AND((NETWORK,UDP),(DST-PORT,443),(NOT(GEOIP,CN)))` → **REJECT**（禁境外 QUIC）
4. 自有服务：`vlook/pc.290490.xyz` → 默认代理；`xx/dsh.290490.xyz` 与 `*.290490.xyz` → 直连
5. `googleapis.cn` → 直连；`speedtest.cn` → ✈️ Speedtest(=DIRECT)
6. `RULE-SET,zdcn` → 直连；`RULE-SET,zdgw` → 默认代理
7. Steam 内容/Cdn 直连，`GEOSITE,steam` → 默认代理
8. AI 固定出口（**必须排在 `GEOSITE,google` 之前**）：`aistudio/makersuite/alkalimakersuite*/generativelanguage` + `GEOSITE,google-gemini` → 🛡️ 稳定固定
9. `GEOSITE,youtube` → 📺 YouTube；`opencode.ai` → 🤖 ChatGPT；`GEOSITE,category-ai-!cn` → 🤖 ChatGPT
10. 流媒体（netflix/disney/spotify/tiktok）、GitHub、Telegram、Twitter、Google、**`GEOSITE,google-cn → 🎯 直连`**、Apple、OneDrive、Microsoft、Oracle、Ookla
11. `RULE-SET,oc-cn-domain → 直连` → `GEOIP,CN → 直连` → `MATCH → 🐟 漏网之鱼`

### 4.5 分组与出口
`🚀 默认代理`（→ ♻️ 香港自动 → `[极速] 🇭🇰 香港02`）、`🛡️ 稳定固定`（→ `🇸🇬 新加坡-自建TLS`）、`♻️ 香港自动`、`🎯 直连`、`🐟 漏网之鱼`、`✈️ Speedtest`(DIRECT)、`📺 YouTube`、`🎬 流媒体`、`🤖 ChatGPT`、`📦 GitHub`、`🔍 Google`、`🪟 微软`、`🍎 Apple`、`🏢 甲骨文 Oracle`、`✈️ Telegram`。

---

## 5. DSH 手机端远程入口

- 地址：`https://dsh.290490.xyz:3081`（Cloudflare 上 `dsh` 的 AAAA 为 **DNS-only**，指向 `pppoe-wan` 的公网 IPv6）
- 路由侧：`/etc/dsh-nginx/` 独立 procd（nginx `[::]:3081` TLS + **Host 强制改写**）→ 反代 PC `192.168.31.218:3081` 的 DSH Pocket
- 证书：`acme.sh`（Let's Encrypt **DNS-01**，Cloudflare，token `/etc/cf-dns.token`）→ `/etc/dsh-nginx/cert/`
- DDNS：`ddns.dsh_ipv6` + `/usr/lib/ddns/update_cloudflare_dsh.sh`（每 5 分钟更新 AAAA）
- 防火墙：`Allow-DSH-Pocket-IPv6`（wan→tcp/3081 ACCEPT，仅 IPv6）
- **为什么必须走 nginx**：DSH Pocket 的 `classifyHost()` 把裸 IPv6 Host 当 loopback 免密；nginx 改写 Host 后，IP 直连也只能看到 PIN 页

---

## 6. 性能基线与测量方法

**直连（LAN→WAN，PC 有线 1G）实测（2026-10-27）**

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

### ★1 硬件流量卸载会压死下行（600M 事故）
- 现象：千兆线路只能跑 ~600，且 CPU 不高、无丢包
- 真因：`flow_offloading_hw=1` 时 fw4 把 flowtable 设备选成**物理口**（`pon0`），而 WAN 是 **`pppoe-wan`**（套在 `pon0.995` 上），硬件快路径对不上 ⇒ 半残卸载，比纯软件转发更慢
- 铁律：`flow_offloading=1` + `flow_offloading_hw=0`
- **判据**：遇到"千兆只跑 600"，**先做 offload A/B**，再怀疑测速站和线路

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
3. `uci show firewall | grep offload` → `1` 和 `0`
4. LuCI → 服务 → Nikki → 点保存不报错
5. `nslookup tablet.lan` → 192.168.31.122
6. 代理：外网首页能开；直连：多源测速 ≥ 850Mbps

### 8.5 常用查询
```sh
nft list table inet fw4 | grep -A5 flowtable         # offload 设备列表
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
| **硬件流量卸载** | ★ 永远别开（§7-1） |
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
| `01-光猫-HG5585F/` | 光猫：刷机流程、**原厂 NAND 全分区备份（CU+CT，唯一副本）**、固件物料、身份数据、串口日志 |
| `02-主路由-AN7581-QWRT/` | QWRT 镜像、固件分析与改造脚本、IRQ/PON 审计报告、配置备份 |
| `03-小米AP-BE6500Pro/` | 无线信道规划审计、WiFi 实测报告 |
| `04-代理-nikki/` | 当前 profile、daed 时代规则快照、DSH Pocket 部署件 |
| `05-网络测绘-netplan/` | 家用 WiFi 测绘工具（survey/index.html） |
| `reports/` | 当前技术栈的过程报告（9 篇，按时间） |
| `tools/` | 探针与一次性脚本（probes/ 下是历史探针） |
| `plugins/` | DSH 插件（dsh-usage-stats）源码 |
