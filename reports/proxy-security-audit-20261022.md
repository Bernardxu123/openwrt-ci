# OpenWrt 代理栈与安全面只读审计报告

- **目标**：烽火 HG5585F CT 版 / QWRT R26.10.21 / airoha-an7581 / 192.168.31.1
- **审计时间**：2026-10-22 00:00 ~ 00:20 (CST)
- **方式**：全程 SSH 只读采集（`python ssh_run.py "命令"`）。**未执行任何 uci set / uci commit / init restart / 文件写入**。
- **基线**：`DISTRIB_RELEASE='25.12.3'` `DISTRIB_REVISION='R26.10.21'` `DISTRIB_TARGET='airoha/an7581'`，kernel `5.4.302`，hostname `Bernardxu`

> **重要前置更正**：任务描述中的 `/etc/config/ssrplus` **不存在**。luci-app-ssr-plus 在本机实际使用的是 **`/etc/config/shadowsocksr`**（49980 字节，62 个 `config servers` 段）。本文所有"ssrplus"均指该文件。生成的运行配置在 `/var/etc/ssrplus/`。

---

## 0. 结论速览表

| # | 现状 | 风险 | 类别 |
|---|---|---|---|
| 1 | telnetd(23) 运行 + UID0 `telnet` 账号口令 = `password` | **高** | 安全面 |
| 2 | vsftpd(21) `0.0.0.0` + write_enable + check_shell=NO + 无 SSL | **高** | 安全面 |
| 3 | samba(139/445) `guest ok` + `guest account=root` + NT1 + 加密关 | **高** | 安全面 |
| 4 | `fullcone=1` 全锥 NAT + `flow_offloading(_hw)=1` | **高** | 安全面 |
| 5 | chatgpt.com 等不在 gfwlist → 走运营商 DNS → 已污染 | **高** | DNS |
| 6 | `ipv6_support=0` + nft `meta nfproto ipv6 return` → IPv6 全直通 | **高** | 分流 |
| 7 | dropbear `RootPasswordAuth=on`，口令 MD5-crypt `$1$` | **高** | 安全面 |
| 8 | 62 节点共用 1 个 UUID | 中 | 代理栈 |
| 9 | 无 DNAT/redirect 规则 + UPnP/xupnpd init 开机自启 | 中 | 安全面 |
| 10 | dnsmasq 监听 WAN 侧 `100.80.214.33:53` | 中 | DNS |
| 11 | ssr-rules 每 300s 自检 + ssr-switch 667s 轮询 | 中 | 代理栈 |
| 12 | 订阅更新每天 02:00 无条件 `shadowsocksr restart` → 每日断流 | 中 | 代理栈 |
| 13 | openclash 残留 10.8M + init 自启 + firewall include 指向不存在文件 | 中 | 冗余 |
| 14 | 无 TR069/ACS/CWMP 残留（干净） | 低（正面） | 安全面 |
| 15 | 无 `/etc/firewall.user`，自定义 nft 仅 ss_spec 表 | 低（正面） | 安全面 |

---

# A. 代理栈实况

## A0. 拓扑纠正：不是 daed，是 ssr-plus + Xray

本机运行中的代理栈（`ps w`）：

```
9279 root  1262m S  /var/etc/ssrplus/bin/v2ray run -c /var/etc/ssrplus/tcp-udp-ssr-retcp.json
9881 root  2304 S  {ssr-rules} /bin/sh /usr/bin/ssr-rules -s 216.236.63.43 -l 1234 -S  -L  -a  -i /etc/ssrplus/china_ssr.txt
9918 root   948 S  /var/etc/ssrplus/bin/dns2tcp -L 127.0.0.1#5335 -R 8.8.4.4#53 -A
10033 root 2088 S  {ssr-switch} /bin/sh /usr/bin/ssr-switch start 667s 5
10234 root 2000 S  {ssr-monitor} /bin/sh /usr/bin/ssr-monitor 0 1 0 0 0 1
```

无 daed / daed-panel / wing.db 相关进程；`/etc/config/` 下也没有 `daed`/`passwall`/`xray` 配置文件。工作区 AGENTS.md 描述的 daed 属旧 LibWrt 拓扑，**不适用于本机**。当前唯一在跑的代理是 **luci-app-ssr-plus + Xray 内核**。

## A1. `/etc/config/shadowsocksr`（即任务中的"ssrplus 配置"）

**全局段（`config global`）**：

```
config global
	option global_server 'cfg214a8f'
	option threads '0'
	option run_mode 'router'
	option dports '2'
	option pdnsd_enable '1'          # 1 = dns2tcp 隧道模式
	option filter_aaaa '1'           # ← 声明过滤 AAAA（但见 A3 实际未生效）
	option ipv6_support '0'          # ← IPv6 不代理（关键，见 C-6）
	option tunnel_forward '8.8.4.4:53'# ← dns2tcp 上游：明文 UDP 53
	option monitor_enable '1'
	option enable_switch '1'
	option switch_time '667'         # ← ssr-switch 轮询周期（秒）
	option switch_timeout '5'
	option switch_try_count '3'
	option default_node_local_port '1234'
	option component_mirror 'direct'
	option gfwlist_url 'https://fastly.jsdelivr.net/gh/YW5vbnltb3Vz/domain-list-community@release/gfwlist.txt'
	option chnroute6_url 'https://raw.githubusercontent.com/1715173329/IPCIDR-CHINA/master/ipv6.txt'
	option chnroute_url 'https://ispip.clang.cn/all_cn.txt'
	option adblock_url 'https://anti-ad.net/anti-ad-for-dnsmasq.conf'
	option old_global_server 'cfg214a8f'
```

**订阅段（`config server_subscribe`）**：

```
config server_subscribe
	option proxy '1'                  # 通过代理订阅
	option auto_update '1'            # 开启自动更新
	option config_auto_update_mode '0'# 0=按 cron 单次，1=loop 每分钟
	option auto_update_week_time '*'
	option auto_update_day_time '2'
	option auto_update_min_time '0'   # → cron: 0 2 * * *（每天 02:00）
	option url_test_url 'https://www.google.com/generate_204'
	option user_agent 'v2rayN/9.99'
	option filter_words '过期/重置/套餐/剩余/网址/QQ群/官网/防失联/回国'

config server_subscribe_item
	option enabled '1'
	option alias '极速'
	option url 'https://hm.zmglqtdbkr.com/jiquan/96c9086f57deae4d3cf4b022cf630ed8'   # HTTPS
```

**访问控制段**：

```
config access_control
	option lan_ac_mode '0'
	option router_proxy '1'
	list wan_fw_ips '149.154.160.0/20'   # Telegram
	list wan_fw_ips '67.198.55.0/24'
	list wan_fw_ips '91.108.4.0/22'      # Telegram
	list wan_fw_ips '91.108.56.0/22'
	list wan_fw_ips '109.239.140.0/24'
	list wan_fw_ips '8.8.8.8'
	list wan_fw_ips '1.1.1.1'
	list Interface 'lan'
```

**其余段**：`socks5_proxy`（server=nil）、`http_proxy`（server=nil）、`server_global`（enable_server=0）、`global_xray_fragment`（fragment=0, noise=0）、`clash_client_group`（enabled=0）。

## A2. 节点列表统计

```
$ grep -c '^config servers' /etc/config/shadowsocksr
62
```

**协议 / 传输 / 安全层分布（62/62 完全一致）**：

```
$ grep -h option.v2ray_protocol /etc/config/shadowsocksr | sort | uniq -c
     62  option v2ray_protocol 'vless'
$ grep -h "option reality " /etc/config/shadowsocksr | sort | uniq -c
     62  option reality '1'
$ grep -h "option tls " /etc/config/shadowsocksr | sort | uniq -c
     62  option tls '0'
$ grep -h option.transport /etc/config/shadowsocksr | sort | uniq -c
     62  option transport 'raw'
$ grep -h option.tls_flow /etc/config/shadowsocksr | sort | uniq -c
     62  option tls_flow 'xtls-rprx-vision'
$ grep -h option.switch_enable /etc/config/shadowsocksr | sort | uniq -c
     62  option switch_enable '1'
```

- **协议**：VLESS + REALITY + xtls-rprx-vision + raw (TCP)，全部 62 个一致，**无一个是传统 SS/SSR/Hysteria/Trojan**
- **TLS**：`option tls '0'` 全部为 0（因为走 REALITY 自带 TLS，ssr-plus 用 `reality` 独立开关表达），REALITY 指纹 `chrome`，伪装 SNI `deltaforce.garena.com`
- **服务器**：仅 **5 个** 不同的域名后端（`bbpd.leen-ttadk.ppsgldass.com` / `lass.sppe-asdd.ppsgldass.com` / `mberw.ppsre-dlmdd.ppsgldass.com` / `xz-il1li1il11li.mlintogaainy.com` + 1 个 nil），62 个节点靠不同端口区分
- **UUID**：**62 个节点共用同一个 UUID**

```
$ grep -h option.vmess_id /etc/config/shadowsocksr | sort -u | wc -l
1
```

> ⚠️ 该 UUID 在本报告全文中一律不输出原文。

**区域分布（按 alias）**：美国 14（01-06 + 3 原生 x15 + 5 国际优化）、香港 10、日本 10、新加坡 6、台湾 7、韩国 1、越南 1、马来 1、澳 1、印尼 1、法 1、英 1、德 1、西 1、荷 1、土 1、加 1、意 1、俄 1、乌 1、葡 1、南非 1。
其中 `switch_enable=1` 的全部 62 个都参与故障切换池。

## A3. 生成配置与 xray 内核

**内核版本**：

```
$ /usr/bin/xray version
Xray 26.6.1 (Xray, Penetrates Everything.) OpenWrt (go1.27.1 linux/arm64)
```

> 注意：工作区 AGENTS.md 记的 VPS 侧 Xray 26.10.10 是**服务端**版本；本机客户端是 **26.6.1**。

**`/var/etc/ssrplus/` 内容**：

```
$ ls -la /var/etc/ssrplus/
drwxr-xr-x  bin/
-rw-r--r--  tcp-udp-ssr-retcp.json      (2198 bytes)
$ ls -la /var/etc/ssrplus/bin/
dns2tcp -> /usr/bin/dns2tcp
v2ray   -> /usr/bin/xray
```

**`tcp-udp-ssr-retcp.json` 关键部分（脱敏）**：

```json
{
  "outbounds": [{
    "protocol": "vless",
    "streamSettings": {
      "network": "raw",
      "sockopt": { "mark": 255 },
      "security": "reality",
      "realitySettings": { "publicKey": "<已脱敏>", "fingerprint": "chrome",
                            "serverName": "deltaforce.garena.com", "shortId": "<已脱敏>" }
    },
    "settings": { "vnext": [{ "port": 31009,
        "users": [{ "flow": "xtls-rprx-vision", "encryption": "none", "id": "<UUID已脱敏>" }] }] },
    "tag": "cfg214a8f:🇸🇬 新加坡01"
  }],
  "log": { "loglevel": "warning" },
  "inbounds": [{
    "port": 1234, "protocol": "dokodemo-door",
    "settings": { "network": "tcp,udp", "followRedirect": true },
    "sniffing": { "enabled": true, "destOverride": ["http","tls","quic"],
                  "domainsExcluded": [ ...23 个 vivox/小米/Apple 域名... ] }
  }]
}
```

> **注意**：这份 JSON 里**没有 `dns` 段、没有 `routing` 段**。即：**routing 不在 xray 内做**，而是由 `ssr-rules` 生成的 nftables/ipset 规则做（见 A5）；DNS 也不在 xray 内做，而是走 dnsmasq + dns2tcp（见 A4）。

**dns2tcp 上游**：

```
/var/etc/ssrplus/bin/dns2tcp -L 127.0.0.1#5335 -R 8.8.4.4#53 -A
```

- `-L 127.0.0.1#5335`：本地 UDP 监听 5335（仅回环，`netstat` 确认 `127.0.0.1:5335`）
- `-R 8.8.4.4#53`：上游是 **Google 8.8.4.4 的明文 UDP/53**（非 DoT/DoH）。该查询由 ssr-plus 的 `tunnel_forward` 决定，且会经 ssr-rules 的透明代理规则走代理隧道（`ss_spec_output` 链把 dport 53 redirect 到 :1234），但**在代理隧道内仍是明文 DNS**——ISP 看不到（在隧道内），但代理服务器与 8.8.4.4 之间是明文。
- `-A`：**启用 AAAA 剥离**（dns2tcp 自身的 `-A` 选项，见 `dns2tcp -h`：`strip all AAAA records from dns response`）

## A4. DNS 解析链路

**dnsmasq 配置（`/etc/config/dhcp`）**：

```
config dnsmasq
	option domainneeded '1'
	option boguspriv '1'
	option localise_queries '1'
	option rebind_protection '1'
	option rebind_localhost '1'
	option local '/lan/'
	option domain 'lan'
	option expandhosts '1'
	option nonegcache '0'
	option cachesize '1000'
	option authoritative '1'
	option readethers '1'
	option leasefile '/tmp/dhcp.leases'
	option resolvfile '/tmp/resolv.conf.d/resolv.conf.auto'
	option nonwildcard '1'
	option localservice '1'
	option ednspacket_max '1232'
	option filter_aaaa '0'     # ← dnsmasq 层 AAAA 过滤关闭
	option filter_a '0'
```

**dnsmasq 的实际运行配置**（`/var/etc/dnsmasq.conf.cfg01411c`）：

```
resolv-file=/tmp/resolv.conf.d/resolv.conf.auto
conf-dir=/tmp/dnsmasq.cfg01411c.d
```

- **无 `noresolv`**、**无全局 `server=` 覆盖** → dnsmasq 默认上游 = `/tmp/resolv.conf.d/resolv.conf.auto`
- 该文件内容 = **运营商 DNS**：

```
# Interface wan
nameserver 210.22.70.225
nameserver 210.22.70.3
# Interface wan6
nameserver 2408:8026:480:112::6666
```

**ssr-plus 注入 dnsmasq 的分域名覆盖**（`/tmp/dnsmasq.cfg01411c.d/dnsmasq-ssrplus.d/`）：

| 文件 | 内容 | 行数/规模 |
|---|---|---|
| `gfw_list.conf` | `server=/<域名>/127.0.0.1#5335` → 走 dns2tcp 隧道 | 17804 行（源文件 35608 行） |
| `gfw_base.conf` | 同上 | 30 条 |
| `applechina.conf` | `server=/<apple域名>/114.114.114.114` | 173 条（Apple 走国内 DNS） |
| `whitelist_forward.conf` | `nftset=/<域名>/4#inet#ss_spec#whitelist_domain` | 7 条 |
| `blacklist_forward.conf` | 空 | 0 |
| `denylist.conf` | `address=/<域名>/` 黑洞 | 13 条（小米/腾讯统计类） |

**过滤 AAAA 的两处开关**：

1. ssr-plus `global.filter_aaaa='1'` → 但 `get_filter_aaaa()` 逻辑是：

```sh
get_filter_aaaa() {
	ipv6_enabled && { echo 0; return; }
	ret="$(uci get "$NAME.@global[0].filter_aaaa" 2>/dev/null)"
	[ -z "$ret" ] && ret="$(uci get "$NAME.@global[0].mosdns_ipv6" 2>/dev/null)"
	echo "${ret:=1}"
}
ipv6_enabled() {
	[ "$(uci_get_by_type global ipv6_support 0)" = "1" ] && [ "$USE_TABLES" = "nftables" ]
}
```

由于 `ipv6_support='0'`，`ipv6_enabled()` 返回假 → 走 `filter_aaaa=1` 分支 → dns2tcp 确实带上了 `-A`（ps 已确认）。**但 dns2tcp 只处理 gfwlist 内的域名**。

2. dnsmasq 层 `filter_aaaa='0'` → **dnsmasq 本身不过滤 AAAA**。

**实测验证（从路由器本机查询 192.168.31.1）**：

```
$ nslookup -type=AAAA www.google.com 192.168.31.1
Non-authoritative answer:
        ← 无任何 Address（AAAA 被 dns2tcp -A 剥掉）

$ nslookup -type=AAAA www.qq.com 192.168.31.1
Address: 2408:873d:a00:1f6::56
Address: 2408:873d:a00:303f::35     ← 国内域名正常返回 AAAA

$ nslookup -type=AAAA www.microsoft.com 192.168.31.1
Non-authoritative answer:  ... (无 Address)
$ nslookup -type=AAAA www.microsoft.com 210.22.70.225   # 运营商 DNS
Address: 2a02:26f0:dc:48d::356e    (5 条)
```

`www.microsoft.com` 在 gfwlist 里（`server=/microsoft.com/127.0.0.1#5335`），走 dns2tcp → AAAA 被剥。
但 `example.org` **不在** gfwlist → 走运营商 DNS → **AAAA 原样返回**：

```
$ nslookup -type=AAAA example.org 192.168.31.1
Address: 2606:4700:10::ac42:9ded
Address: 2606:4700:10::6814:1a88
```

**结论**：AAAA 过滤**只对 gfwlist 内的域名生效**，不在 gfwlist 的境外域名仍会拿到 AAAA。而 `ipv6_support=0` 又意味着这些 AAAA 对应的 IPv6 流量会**直接出网不代理**（见 C-6）。

## A5. 路由（gfwlist / chnroute）——不在 xray 内，在 nftables

`/etc/ssrplus/` 下的规则源文件：

```
-rw-rw-r--  china6_ssr.txt        18122   (IPv6 chnroute, 格式 2001:250::/30)
-rw-rw-r--  china_ssr.txt        134054   (IPv4 chnroute)
-rw-rw-r--  gfw_list.conf        1215374  (源, 35608 行)
-rw-rw-r--  gfw_base.conf           3542
-rw-rw-r--  white.list                85
-rw-rw-r--  deny.list                334
-rw-rw-r--  black.list                 0
-rw-rw-r--  ad.conf                    0
-rw-rw-r--  applechina.conf         8460
-rw-rw-r--  mosdns-config.yaml        826   (mosdns 未启用，残留)
-rw-rw-r--  dnsproxy_dns.list        1149   (10 个 DoH sdns:// 模板，dnsproxy 未启用，残留)
-rw-rw-r--  clash/                       (clash_client_group enabled=0，残留)
```

**实际生效的 nftables 表**（`nft list tables`）：

```
table inet fw4
table inet ss_spec
table ip ss_spec_mangle
```

`inet ss_spec` 的关键链：

```
chain ss_spec_wan_fw {
	tcp dport { 22, 53, 80, 143, 443, 465, 587, 853, 993, 995, 9418 } counter packets 1620 bytes 96292 redirect to :1234
}

chain ss_spec_wan_ac {
	tcp dport 53 ip daddr 127.0.0.0/8 return
	tcp dport != 53 ip daddr 216.236.63.43 return      ← 代理服务器 IP 直连（防环路）
	ip daddr @blacklist jump ss_spec_wan_fw
	ip daddr @whitelist return
	ip daddr @whitelist_domain return
	ip saddr @fplan jump ss_spec_wan_fw
	ip saddr @bplan return
	meta l4proto tcp ip daddr @music return
	ip daddr @ss_spec_wan_ac return
	ip daddr @china return                              ← chnroute 直连
	ip saddr @gmlan ip daddr != @china jump ss_spec_wan_fw
	jump ss_spec_wan_fw
}

chain ss_spec_prerouting {
	type nat hook prerouting priority filter; policy accept;
	meta nfproto ipv6 return                            ← ⚠️ IPv6 全部放行
	ip daddr 0.0.0.0/8 return ... (私网段 return)
	iifname "br-lan" tcp dport { 22, 53, 80, 143, 443, 465, 587, 853, 993, 995, 9418 } jump ss_spec_wan_ac
}

chain ss_spec_output {
	type nat hook output priority filter; policy accept;
	meta nfproto ipv6 return                            ← ⚠️ IPv6 全部放行
	meta mark 0x000000ff return                          ← 代理自身流量防环路
	... tcp dport { 22, 53, 80, ... } jump ss_spec_wan_ac
}
```

`ip ss_spec_mangle`（UDP TPROXY）：

```
chain ss_spec_tproxy {
	... ip daddr 216.236.63.43 return
	meta l4proto udp ip saddr @bplan return
	meta l4proto udp ip daddr @ss_spec_wan_ac return
	meta l4proto udp ip daddr @china return
	udp dport 80 counter packets 0 bytes 0 drop
	udp dport 443 counter packets 264 bytes 337538 drop     ← 全局禁 QUIC
}
chain prerouting {
	type filter hook prerouting priority mangle; policy accept;
	iifname "br-lan" udp dport { 22, 53, 80, 143, 443, 465, 587, 853, 993, 995, 9418 } jump ss_spec_tproxy
}
```

**ss_spec 集合**：`china`（chnroute）、`gmlan`、`fplan`、`bplan`、`whitelist`、`blacklist`、`music`、`whitelist_domain`、`ss_spec_wan_ac`。
**`ss_spec_wan_ac` 内容**：`0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.88.99.0/24, 192.168.0.0/16, 198.18.0.0/15, 198.51.100.0/24, 203.0.113.0/24, 216.236.63.43, 224.0.0.0/3`。
> 注意：**没有 `gfwlist` 集合**。因为 `run_mode='router'`（不是 gfw），gfw2ipset.sh 在非 gfw 模式下会 `sed -i '/^[[:space:]]*\(ipset=\|nftset=\)/d'` 清理掉 gfwlist 引用，只保留 `server=` 的 DNS 分流。当前是 **router 模式 + chnroute IP 分流**（国内 IP 直连、其余走代理），不是 gfwlist 模式。

## A6. 三个守护脚本的作用与 667s 轮询影响

### `ssr-rules`（63KB）— 透明代理规则生成器
头注释：
```sh
#!/bin/sh
# Copyright (C) 2017 openwrt-ssr
# Copyright (C) 2017 yushi studio <ywb94@qq.com>
# This is free software, licensed under the GNU General Public License v3.
```
作用：根据 `run_mode` / chnroute / gfwlist / 白黑名单，用 nftables（或 iptables）建立 `inet ss_spec` + `ip ss_spec_mangle` 两张表，把 LAN 客户端的 TCP/UDP 透明重定向到 xray 的 1234 端口。当前以 `-s 216.236.63.43 -l 1234 -i /etc/ssrplus/china_ssr.txt` 运行（`216.236.63.43` 即代理服务器 IP，已脱敏语境下的必要标识）。

### `ssr-switch`（6.6KB）— 故障切换（667s 轮询）
头注释同上（openwrt-ssr / yushi studio）。核心循环：

```sh
start() {
	while [ "1" = "1" ]; do
		sleep "0000$cycle_time"
		run_once
	done
}
```

参数解析：`ssr-switch start 667s 5` → `ORIG_ARG2=667s` → `cycle_time=667`（轮询间隔）、`ORIG_ARG3=5` → `switch_time=5`（curl 超时秒）。对应 UCI `switch_time=667`、`switch_timeout=5`、`switch_try_count=3`。

`run_once()` 逻辑：
1. `check_direct_probe()` —— **直连**（不经代理）curl `https://www.google.com/generate_204`，5s 超时。成功则 `direct_fail_count=0` 并直接 return。
2. 连续失败累计到 `direct_fail_limit=3`（`switch_try_count`）后，才 `test_proxy "$CURRENT_SERVER"`。
3. 当前节点也失败 → `select_proxy` 遍历 `switch_enable=1` 的节点逐个测 → `switch_proxy` 执行 `set_main_server` + **`/etc/init.d/shadowsocksr restart`**。

**667s 轮询会不会造成周期性断流？—— 答：正常情况下不会。**

证据：
```
$ ps w | grep ssr-switch
10033 root 2088 S {ssr-switch} /bin/sh /usr/bin/ssr-switch start 667s 5
$ ps w | grep "sleep 0000"
26390 root 1332 S sleep 0000667s          ← 正在睡 667s 周期
$ logread | grep -i "Switch to" | tail -30
(无输出)                                ← 从未触发过切换
$ logread | grep -i ssrplus | tail -30
(无输出)
```

`/var/log/ssrplus.log` 中也**没有任何 "Switch to" / "Current server error" 记录**。

但有两个真实的周期性副作用：

**(a) ssr-switch 每 667s 会发一次直连探测**（`curl --connect-timeout 5 --max-time 5 https://www.google.com/generate_204`）。因为路由器自身出口走 `ss_spec_output` 链（`tcp dport 443 ... jump ss_spec_wan_ac`），**这次"直连探测"实际也会被代理**（google.com 不在 chnroute → 走代理）。所以它探测的是"代理是否通"，而非真正的"直连是否通"。这是逻辑上的小瑕疵，不造成断流。

**(b) `ssr-rules` 每 300s 跑一次自检 + 持久化重写**：

```sh
AUTO_UPDATE_INTERVAL=300  # auto-update check interval (seconds)
...
while true; do
	sleep "$AUTO_UPDATE_INTERVAL"
	if /usr/bin/ssr-rules -C >/dev/null 2>&1; then
		logger -t ssr-rules[daemon] "Rules status OK, no update needed"
	else
		logger -t ssr-rules[daemon] "Rules changed or missing, updating persistence"
		if /usr/bin/ssr-rules -P >/dev/null 2>&1; then ...
```

`-P` = `force_update_persistence()` → **删除并重写** `/usr/share/nftables.d/ruleset-post/99-shadowsocksr.nft`（192KB）。日志证实每 5 分钟一次：

```
$ tail -40 /var/log/ssrplus.log
2026-10-21 21:02:11: -----------end------------
2026-10-21 21:07:07: ssr-rules: Using nftables
2026-10-21 21:12:08: ssr-rules: Using nftables
2026-10-21 21:17:08: ssr-rules: Using nftables
...（每 5 分钟一次，直到 23:57:28）
```

> ⚠️ 这意味着**每 5 分钟会重写一次 nftables 持久化文件**。`-P` 只写文件不重载规则（不 apply），所以不产生断流，但 192KB 文件 / 5 分钟的写放大对 flash 有磨损，且 `rm -f` + 重写之间若恰好触发防火墙重载会有窗口期。

### `ssr-monitor`（7.9KB）— 进程守护
头注释同上。作用：每 30s 检查关键进程存活，死了就 `/etc/init.d/shadowsocksr restart`：

```sh
while [ "1" == "1" ]; do
	sleep 000030s
	if [ "$redir_tcp_process" -gt 0 ]; then
		icount=$(redir_tcp_running)
		[ "$icount" -lt "$tcp_expected" ] && { ...; /etc/init.d/shadowsocksr restart; exit 0; }
	fi
	...
	if [ "$pdnsd_process" -eq 1 ]; then      # dns2tcp 存活检查
		icount=$(ps_list | grep $TMP_BIN_PATH/dns2tcp | grep -v grep | wc -l)
		[ "$icount" -lt 1 ] && { kill -9 ...; start_dns2tcp "$dnsserver"; }
	fi
```

当前参数 `ssr-monitor 0 1 0 0 0 1` = server_count=0, redir_tcp=1, redir_udp=0, kcp=0, local=0, **pdnsd=1（dns2tcp 守护开启）**。

## A7. 订阅更新机制

**cron**：

```
$ crontab -l
0 2 * * * echo "" > /tmp/log/msd_lite.log
0 4 * * * /etc/coremark.sh
0 2 * * * /usr/share/shadowsocksr/ssrplusupdate.sh >/var/log/ssrplus.log
```

这条 `0 2 * * *` 由 ssr-plus 的 `add_cron()` 依据 `auto_update_min_time=0 / auto_update_day_time=2 / auto_update_week_time=*` 生成。

**`ssrplusupdate.sh` 内容概要**：

```sh
LOCK_DIR="/var/run/ssrplusupdate.lock"
MODE="$(uci -q get shadowsocksr.@server_subscribe[0].config_auto_update_mode ...)"
mkdir "$LOCK_DIR" 2>/dev/null || exit 0
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT INT TERM
# (loop 模式：按 config_update_interval 分钟节流，当前 MODE=0 不走)
/usr/bin/lua /usr/share/shadowsocksr/update.lua        # 更新 gfwlist/chnroute/apple/adblock
sleep 2s
/usr/share/shadowsocksr/chinaipset.sh /var/etc/ssrplus/china_ssr.txt   # 重建 chnroute ipset
sleep 2s
/usr/bin/lua /usr/share/shadowsocksr/subscribe.lua      # 更新订阅节点
```

**`update.lua` 下载（全部 HTTPS，但 `curl --insecure`）**：

```sh
local refresh_cmd = "curl -sSL --insecure -o /tmp/ssr-update." .. type .. " " .. url
update(chnroute6_url, "/etc/ssrplus/china6_ssr.txt", ...)
update(gfwlist_url,  "/etc/ssrplus/gfw_list.conf", ...)
update(chnroute_url, "/etc/ssrplus/china_ssr.txt", ...)
update(apple_url,    "/etc/ssrplus/applechina.conf", ...)
update(adblock_url,  "/etc/ssrplus/ad.conf", ...)
```

→ `fastly.jsdelivr.net` / `raw.githubusercontent.com` / `ispip.clang.cn` / `anti-ad.net`，**全 HTTPS**，但 `--insecure` 跳过证书校验（可被中间人替换 gfwlist/chnroute 内容）。

**`subscribe.lua` 抓取订阅**：

```sh
local cmd = string.format(
	'curl -sSL --http1.1 --connect-timeout 20 --max-time 30 --retry 3 -H "Accept-Encoding: identity" %s --insecure --location %s',
	ua_opt, safe_url)
```

- 订阅 URL 是 **HTTPS**（`https://hm.zmglqtdbkr.com/jiquan/...`）✅
- UA = `v2rayN/9.99`
- **`--insecure`**：同样跳过 TLS 校验 → 订阅内容（节点 URL/UUID）可被中间人读取或篡改
- 订阅转换服务默认值 `https://api.asailor.org/sub`（`sub_convert` 未启用，不走）

**订阅更新结尾会重启代理**（这是每日断流的来源）：

```lua
-- subscribe.lua:2980 附近
if not ucic:get(name, globalServer) then
	luci.sys.call("/etc/init.d/" .. name .. " stop ...")
	ucic:set(name, ..., 'global_server', firstServer); ucic:commit(name)
	luci.sys.call("/etc/init.d/" .. name .. " start ...")
else
	log('维持当前主服务器节点。')
	luci.sys.call("/etc/init.d/" .. name .. " restart > /dev/null 2>&1 &")   ← 无条件 restart
end
```

→ **每天 02:00 必然执行一次 `shadowsocksr restart`**，无论节点列表是否变化。这会造成一次全量断流（重启 xray + 重建 nft 规则 + 重启 dnsmasq）。

---

# B. 安全面

## B1. 监听端口全表

```
$ netstat -tulnp
Proto Local Address            State    PID/Program
tcp  0.0.0.0:80                LISTEN   3223/uhttpd
tcp  127.0.0.1:53              LISTEN   10193/dnsmasq
tcp  192.168.31.1:53           LISTEN   10193/dnsmasq
tcp  100.80.214.33:53          LISTEN   10193/dnsmasq      ← ⚠️ WAN 侧 CGNAT 地址
tcp  0.0.0.0:21                LISTEN   3285/vsftpd        ← ⚠️
tcp  0.0.0.0:22                LISTEN   2454/dropbear
tcp  0.0.0.0:445               LISTEN   3420/smbd          ← ⚠️
tcp  0.0.0.0:139               LISTEN   3420/smbd          ← ⚠️
tcp  :::80                      LISTEN   3223/uhttpd
tcp  :::1234                    LISTEN   9279/v2ray         ← 代理入站，IPv6 也开
tcp  :::22                      LISTEN   2454/dropbear
tcp  :::23                      LISTEN   3108/telnetd       ← ⚠️
tcp  :::445                     LISTEN   3420/smbd          ← ⚠️
tcp  :::139                     LISTEN   3420/smbd          ← ⚠️
tcp  ::1:53 / fe80::*:53 / 2408:820c:820a:a300::1:53 / fdae:8777:3859::1:53 / 2408:820c:8200:...:53
                                        LISTEN   10193/dnsmasq  ← ⚠️ IPv6 DNS 全开
udp  192.168.31.255:137/138, 192.168.31.1:137/138, 0.0.0.0:137/138   3421/nmbd   ← ⚠️
udp  127.0.0.1:5335            LISTEN   9918/dns2tcp
udp  0.0.0.0:67                 LISTEN   10193/dnsmasq
udp  :::1234                    LISTEN   9279/v2ray
udp  :::546 / :::547                       7758/odhcp6c / 2886/odhcpd
```

**未监听的（配置存在但没跑）**：`miniupnpd`（upnpd `enabled=0`）、`xupnpd`（`enabled=0`）、`openvpn`（3 个实例全 `enabled=0`）、`microsocks`（`enabled=0`）、`3proxy`（`enabled=0`）、`vlmcsd`（`enabled=0`）、`msd_lite`（`enable=0`）、`openclash`（`config.enable=0`，无进程）。

## B2. `/etc/config/firewall` 完整内容

```uci
config defaults
	option syn_flood '1'
	option input 'REJECT'
	option output 'ACCEPT'
	option forward 'REJECT'
	option tcpcca 'cubic'
	option flow_offloading '1'      ← ⚠️ 软件流卸载
	option flow_offloading_hw '1'   ← ⚠️ 硬件流卸载
	option fullcone '1'             ← ⚠️ 全锥 NAT（IPv4）
	option fullcone6 '0'

config zone
	option name 'lan'
	list network 'lan'
	option input 'ACCEPT'
	option output 'ACCEPT'
	option forward 'ACCEPT'

config zone
	option name 'wan'
	list network 'wan'
	list network 'wan6'
	option input 'REJECT'
	option output 'ACCEPT'
	option forward 'REJECT'
	option masq '1'
	option mtu_fix '1'

config forwarding
	option src 'lan'
	option dest 'wan'

config rule  Allow-DHCP-Renew   (wan/udp/68 → ACCEPT)
config rule  Allow-Ping         (wan/icmp echo-request → ACCEPT)
config rule  Allow-IGMP         (wan/igmp → ACCEPT)
config rule  Allow-DHCPv6       (wan/udp/546 → ACCEPT)
config rule  Allow-MLD          (wan/icmpv6 130/131/132/143 → ACCEPT)
config rule  Allow-ICMPv6-Input (wan/icmpv6 多种，limit 1000/sec)
config rule  Allow-ICMPv6-Forward (wan→* icmpv6，limit 1000/sec)
config rule  Allow-IPSec-ESP    (wan→lan esp → ACCEPT)
config rule  Allow-ISAKMP       (wan→lan udp/500 → ACCEPT)
config rule 'upnp_ssdp_notrack' (lan udp 239.255.255.250:1900 → NOTRACK)
config rule 'wsd_ipv4_notrack'  (lan udp 239.255.255.250:3702 → NOTRACK)
config rule 'wsd_ipv6_notrack'  (lan udp ff02::c:3702 → NOTRACK)

config include 'openclash'
	option type 'script'
	option path '/var/etc/openclash.include'      ← ⚠️ 文件不存在
config include 'shadowsocksr'
	option type 'script'
	option path '/var/etc/shadowsocksr.include'   ← 存在
config include 'luci_iptv'
	option type 'nftables'
	option position 'ruleset-append'
	option path '/etc/iptv.nft'
	option enabled '0'
```

**要点**：
- **完全没有 `config redirect` 段** → 无任何端口转发（这是好事，见 C-9）
- `fullcone '1'` + `fullcone6 '0'`
- `flow_offloading '1'` + `flow_offloading_hw '1'` — 与工作区 AGENTS.md 里"不要开 flow_offloading_hw"的告诫**相冲突**（那是针对旧 LibWrt + dae eBPF 场景；本机是 ssr-plus/nftables，但 hw offload 与 nft redirect 组合仍需实测）
- `openclash` include 指向 `/var/etc/openclash.include`，**该文件不存在**（`ls` 报错）→ fw4 每次重载会尝试读一个缺失的脚本

**fw4 实际生成的链**：

```
chain input {
	type filter hook input priority filter; policy drop;
	iif "lo" accept
	ct state vmap { established : accept, related : accept }
	tcp flags & (fin|syn|rst|ack) == syn jump syn_flood
	iifname "br-lan" jump input_lan
	iifname "pppoe-wan" jump input_wan
	jump handle_reject
}
chain input_wan {
	... Allow-DHCP-Renew / Allow-Ping / Allow-IGMP / Allow-DHCPv6 / Allow-MLD / Allow-ICMPv6-Input
	ct status dnat accept
	jump reject_from_wan
}
chain input_lan { jump accept_from_lan }

table inet fw4:
	flowtable ft { hook ingress priority filter; devices = { lan1..lan4, pon0, ra0, rai0 }; flags offload }
```

**全锥 NAT 的 nft 实现**：

```
meta nfproto ipv4 fullcone comment "!fw4: Handle wan IPv4 fullcone NAT dstnat traffic"
meta nfproto ipv4 fullcone comment "!fw4: Handle wan IPv4 fullcone NAT srcnat traffic"
```

## B3. `/etc/config/system` 与 `uci show system`

**完整内容**（无 telnet/ftp/smb/upnp 开关）：

```uci
config system
	option hostname 'Bernardxu'
	option timezone 'CST-8'
	option ttylogin '0'          ← telnet 登录走 ash --login 分支的前提
	option log_size '64'
	option urandom_seed '0'
	option zram_comp_algo 'lzo'
	option zram_comp_streams '4'
	option zonename 'Asia/Shanghai'
	option log_proto 'udp'
	option conloglevel '8'
	option cronloglevel '7'

config timeserver 'ntp'
	list server 'ntp.tencent.com'
	list server 'ntp1.aliyun.com'
	list server 'ntp.ntsc.ac.cn'
	list server 'cn.ntp.org.cn'

config led 'led_wlan'   (sysfs blue:wlan, dev ra0)
config led 'led_usb1'   (port usb3-port1, usb4-port1)
config led 'led_pon'    (trigger pon0-registration)
config led 'led_los'    (trigger pon0-los)
```

**`uci show system` 与 `/etc/config/system` 完全一致，无额外改动项**；`uci changes` 为**空**（无未提交的 UCI 变更）。

**telnet/ftp/smb/upnp 开关实际在各服务的独立 UCI 里**：

| 服务 | 配置文件 | 关键项 |
|---|---|---|
| telnetd | 无 UCI 开关 | init 脚本硬编码 `procd_set_param command "$PROG" -F -l /bin/login.sh`，**无 `enabled` 概念** |
| vsftpd | `/etc/config/vsftpd` | `option disabled '0'`（**启用**），`option conf_file '/etc/vsftpd.conf'`，`option mdns '0'` |
| samba | `/etc/config/samba` | `option enabled '1'`（**启用**），`homes='0'`，`autoshare='1'`，name='QWRT'，workgroup='WORKGROUP' |
| upnpd | `/etc/config/upnpd` | `option enabled 0`（**禁用**），但 `enable_natpmp 1` / `enable_upnp 1` / `secure_mode 1` / `port 5000` / `internal_iface lan` / perm_rule 允许 1024-65535 |
| xupnpd | `/etc/config/xupnpd` | `option enabled '0'`（**禁用**），`autoactivate '1'` |
| miniupnpd | 同 upnpd | `config_get_bool enabled config enabled 1` → upnpd.enabled=0 → init 直接 return 1（不启动） |

**init 开机自启状态**（`/etc/rc.d/`）：

```
S50telnetd  S50vsftpd  S50xupnpd  S60samba  S94miniupnpd  S95microsocks
S90openvpn  S90vlmcsd  S99msd_lite  S993proxy  S99openclash  S95shadowsocksr
```

→ **telnetd / vsftpd / samba / miniupnpd / xupnpd 的 init 全部开机自启**（虽然 upnpd/xupnpd 的 config 里 enabled=0 使其启动即退出，但 telnetd/vsftpd/samba 是真开）。

**其他遗留服务的 config**：

```uci
# /etc/config/microsocks : enabled 0, port 1080, internet_access 0
# /etc/config/3proxy      : enabled 0
# /etc/config/vlmcsd      : enabled 0, internet_access 0
# /etc/config/msd_lite    : enable 0, port 7088, source eth2
# /etc/config/rtp2httpd   : disabled 1
# /etc/config/openvpn     : custom_config/sample_server/sample_client 全 enabled 0
# /etc/config/ddns        : 全是 yourhost.example.com / your_username 占位符（未启用）
```

## B4. 密码哈希与登录

**`/etc/passwd`**：

```
root:x:0:0:root:/root:/bin/ash
telnet:x:0:0:root:/root:/bin/ash      ← ⚠️ UID=0、GID=0 的第二个 root 账号
daemon:*:1:1:daemon:/var:/bin/false
ftp:*:55:55:ftp:/home/ftp:/bin/false
network:*:101:101:network:/var:/bin/false
nobody:*:65534:65534:nobody:/var:/bin/false
ntp:x:123:123:ntp:/var/run/ntp:/bin/false
dnsmasq:x:453:453:dnsmasq:/var/run/dnsmasq:/bin/false
ubus:x:81:81:ubus:/var/run/ubus:/bin/false
```

**`/etc/shadow` 哈希类型**：

```
$ cut -d: -f2 /etc/shadow | cut -c1-6
$1$NKW      ← root：MD5-crypt (crypt $1$)
$1$V4U      ← telnet：MD5-crypt (crypt $1$)
*
*
*
*
x
x
x
```

- **root 用 `$1$`（MD5-crypt，弱）**，无 `$5$`/`$6$`
- 验证 root 哈希确实对应已知口令：

```
$ openssl passwd -1 -salt <root_salt> "Qazswxdecf1"
>>> confirmed: /etc/shadow root hash == Qazswxdecf1 (MD5-crypt)
```

**⚠️ telnet 账号口令实测 = `password`**：

```
$ t=$(grep "^telnet:" /etc/shadow | cut -d"$" -f3)   # salt = V4UetPzk
$ full=$(grep "^telnet:" /etc/shadow | cut -d: -f2)
$ for pw in admin root 123456 password telnet ... ; do
      h=$(openssl passwd -1 -salt "$t" "$pw")
      [ "$h" = "$full" ] && echo ">>> MATCH FOUND: telnet password = $pw"
  done
>>> MATCH FOUND: telnet password = password
```

**telnetd 是否需要密码 —— 需要，但等效于无口令**：

telnetd 用 `-l /bin/login.sh`；`/bin/login.sh` 逻辑：

```sh
if ( ! grep -qs '^root:[!x]\?:' /etc/shadow || \
     ! grep -qs '^root:[!x]\?:' /etc/passwd ) && \
   [ -z "$FAILSAFE" ]
then
	busybox login          ← 走这里
else
	... exec /bin/ash --login
fi
```

实测分支判定：

```
$ grep -qs "^root:[!x]\?:" /etc/shadow; echo $?
1                              ← shadow 里 root 有真实哈希（不匹配空密码模式）
$ grep -qs "^root:[!x]\?:" /etc/passwd; echo $?
0                              ← passwd 里 root 是 "root:x:..." 匹配到了
$ if ( ! grep -qs ... /etc/shadow || ! grep -qs ... /etc/passwd ) && [ -z "$FAILSAFE" ]; then ...
BRANCH=busybox_login (PASSWORD REQUIRED)
```

→ 走 `busybox login`，**会要求输入用户名+密码**。但因为存在 **UID=0 的 `telnet` 账号、且口令是 `password`**，任何人 `telnet 192.168.31.1` 用 `telnet/password` 即可获得 **root shell**（该账号 shell 是 `/bin/ash`，home 是 `/root`）。这是**等效于无口令 root** 的后门级配置。

**dropbear**：

```uci
config dropbear
	option PasswordAuth 'on'      ← 允许密码认证
	option RootPasswordAuth 'on'  ← ⚠️ 允许 root 密码直接登录
	option Port         '22'
#	option BannerFile   '/etc/banner'
```

```
$ ps w | grep dropbear
2454 root 1116 S /usr/sbin/dropbear -F -P /var/run/dropbear.1.pid -p 22 -K 300 -T 3
25692 root 1140 S /usr/sbin/dropbear -F -P /var/run/dropbear.1.pid -p 22 -K 300 -T 3 -2 9
```

（`-2 9` / `-2 10` 是活动会话。`-K 300` = 300s 免重连保活，`-T 3` = 3s 登录宽限。）

## B5. TR069 / 运营商管理通道

```
$ grep -rIl -i -E "tr069|cwmp|acs_url|acsusername|acs_password|tr-069|easycwmp" /etc
(无输出)
$ grep -rI -i -E "tr069|cwmp|acs" /etc/config /etc/init.d
（命中的全是 dnsmasq/openclash 里的 "macs"/"mac" 子串误匹配，与 ACS 无关）
$ ls /etc/init.d/ | grep -iE "tr069|cwmp|acs|omci"
(无输出)
$ ls /etc/ | grep -iE "omci|tr069|pon"
(无输出)
$ ls /usr/sbin/*tr069* /usr/bin/*tr069*
(无输出)
$ logread | grep -iE "tr069|cwmp|acs"
(无输出)
```

**结论：本机无任何 TR069/CWMP/ACS 配置、守护进程或日志痕迹。** 刷成 QWRT 后原厂 CT 的 TR069 通道已不复存在。

**PON 侧仍有 CTC 运营商标识**（属正常 ONT 必需，非 TR069）：

```uci
# /etc/config/pon
config xpon 'line0'
	option device 'pon0'
	option mode 'epon-10g-1g'
	option serial_number '46485454c1c6acaa'
config omci 'line0_omci'
	option line 'line0'
	option device 'omci0'
	option omcc_version '0xb0'
	option disable_enhanced_security '0'
config oam 'line0_oam'
	option line 'line0'
	option device 'oam0'
	option ctc_oui '111111'
	option ctc_versions '21 30'
	option operator 'ctc'
	option loid '000000000000000014509791'
```

`option operator 'ctc'` + LOID 说明这仍是**注册在联通 CTC 的 ONT**——只要 PON 注册未被运营商解除，联通侧仍可对该 ONT 做局方侧管理（这一层不受本机配置控制）。VLAN 28（TR069 常用）在 `/etc/config/network` 与 `/etc/config/` 中**均无** vlan 配置。

## B6. 自定义防火墙规则

```
$ ls -la /etc/firewall.user
ls: /etc/firewall.user: No such file or directory

$ ls -la /var/etc/*.include
-rwxr-xr-x 550 /var/etc/shadowsocksr.include

$ cat /var/etc/shadowsocksr.include
#!/bin/sh
# Clear existing ss_spec tables
nft delete table inet ss_spec 2>/dev/null
nft delete table ip ss_spec 2>/dev/null
nft delete table ip ss_spec_mangle 2>/dev/null
# Restore shadowsocks nftables rules from persistent file
if [ -f "/usr/share/nftables.d/ruleset-post/99-shadowsocksr.nft" ]; then
	nft -f /usr/share/nftables.d/ruleset-post/99-shadowsocksr.nft
else
	nft list ruleset | awk '/^table (inet|ip) ss_spec/{flag=1} ...' | nft -f -
fi
```

```
$ ls -la /usr/share/nftables.d/ruleset-post/
-rw-r--r-- 192570  99-shadowsocksr.nft
```

**无 `/etc/firewall.user`**；唯一的自定义 nft 持久化就是 ssr-plus 自己那张表（192KB，每 5 分钟被重写一次，见 A6）。

---

# C. 结论（现状 → 风险等级 → 证据 → 建议动作）

## C-1　telnetd(23) + UID0 telnet 账号口令 `password` → **高**

**现状**：`telnetd -F -l /bin/login.sh` 在 `:::23` 监听；`/etc/passwd` 有 `telnet:x:0:0:root:/root:/bin/ash`；该账号 shadow 哈希为 `$1$`，实测明文口令 = `password`。

**证据**：
```
$ netstat -tulnp | grep 23
tcp  0  0  :::23   :::   LISTEN   3108/telnetd
$ ps w | grep telnetd
3108 root 1332 S /usr/sbin/telnetd -F -l /bin/login.sh
$ grep "^telnet:" /etc/passwd
telnet:x:0:0:root:/root:/bin/ash
$ openssl passwd -1 -salt V4UetPzk password
>>> MATCH FOUND: telnet password = password
$ grep -qs "^root:[!x]\?:" /etc/shadow; echo $?   → 1 (root 有真实哈希)
$ grep -qs "^root:[!x]\?:" /etc/passwd; echo $?   → 0
BRANCH=busybox_login (PASSWORD REQUIRED)
```

**风险**：虽然 login.sh 会要求密码，但存在 **UID=0 + 弱默认口令** 的账号 → 任何人可用 `telnet/telnet` 之外的 `telnet/password` 组合拿到 **root shell**（home `/root`，shell `/bin/ash`）。密码在网络上是**明文传输**（telnet 无 TLS）。这是典型的厂商后门模式，且 `/etc/init.d/telnetd` 无 `enabled` 开关、init 开机自启，无法通过 LuCI 一键关闭。

**建议动作**：
1. 立即 `/etc/init.d/telnetd disable` + `stop`（**注意：`/etc/init.d/telnetd` 无 UCI 开关，需用 `disable`/`stop` 命令**；持久化需在 sysupgrade.conf 加 keep 或自建 rc.local 兜底）。
2. 删除 UID0 的 telnet 账号：`sed -i '/^telnet:/d' /etc/passwd` 并同步 `/etc/shadow`。
3. 若必须保留应急通道，改用 dropbear（22）+ 密钥登录，并关闭 `RootPasswordAuth`。
4. 顺手把 root 口令从 MD5-crypt 升级为 yescrypt（`passwd` 后确认 `$y$`）。

## C-2　vsftpd(21) 明文可写 root FTP → **高**

**现状**：`0.0.0.0:21` 监听，`local_enable=YES` + `write_enable=YES` + `check_shell=NO` + `local_umask=022`，**SSL 段全被注释**（`ssl_enable` 未启用），**无 chroot**。

**证据**：
```
$ netstat -tulnp | grep ":21"
tcp  0  0  0.0.0.0:21   0.0.0.0:*   LISTEN   3285/vsftpd
$ ps w | grep vsftpd
3285 root 1032 S /usr/sbin/vsftpd /etc/vsftpd.conf
$ cat /etc/config/vsftpd
config global 'global'
	option disabled '0'
	option mdns '0'
	option conf_file '/etc/vsftpd.conf'
$ grep -n -E "local_enable|write_enable|check_shell|anonymous_enable|ssl_enable|chroot" /etc/vsftpd.conf
anonymous_enable=NO
local_enable=YES
write_enable=YES
check_shell=NO
local_umask=022
#ssl_enable=YES     ← 未启用
（无 chroot_local_user）
```

**风险**：root 账号（shell `/bin/ash`）在 `check_shell=NO` 下**允许 FTP 登录**，可**读写整个文件系统**；口令与数据全明文（FTP 无 TLS）；`local_umask=022` 意味着上传文件默认全局可读。LAN 内任一被攻陷设备可直接取走 `/etc/shadow`、节点 UUID、订阅链接。

**建议动作**：
1. `/etc/config/vsftpd` 置 `option disabled '1'`（或 `stop` + `disable`）——如需保留则**必须**开 `ssl_enable=YES` 并强制 `force_local_logins_ssl=YES`。
2. 若保留：加 `chroot_local_user=YES` + `allow_writeable_chroot=NO`，并新建非 root 的专用 FTP 用户。
3. `local_umask=022` → 改 `077`。

## C-3　samba(139/445) guest 映射到 root + NT1 + 加密关闭 → **高**

**现状**：`smbd` 在 `0.0.0.0:445`、`0.0.0.0:139`、`:::445`、`:::139` 监听，`nmbd` 在 `0.0.0.0:137/138` 广播。smb.conf：

```
guest account = root        ← ⚠️
guest ok = yes              ← ⚠️
map to guest = Bad User     ← ⚠️ 任何无效用户名都映射到 guest(=root)
null passwords = yes        ← ⚠️
security = user
server min protocol = NT1   ← ⚠️ SMB1 仍允许
smb encrypt = disabled      ← ⚠️
writeable = yes
interfaces = 127.0.0.1/8 lo 192.168.31.1/24 fdae:8777:3859::1/60 br-lan
```

**证据**：
```
$ netstat -tulnp | grep -E ":(139|445)"
tcp  0  0  0.0.0.0:445   LISTEN 3420/smbd
tcp  0  0  0.0.0.0:139   LISTEN 3420/smbd
tcp  0  0  :::445        LISTEN 3420/smbd
tcp  0  0  :::139        LISTEN 3420/smbd
udp  0  0  0.0.0.0:137   3421/nmbd
$ grep -E "guest|map to guest|null passwords|min protocol|smb encrypt" /etc/samba/smb.conf
	guest account = root
	guest ok = yes
	map to guest = Bad User
	null passwords = yes
	server min protocol = NT1
	smb encrypt = disabled
$ cat /etc/config/samba
	option 'enabled' '1'
	option 'homes' '0'
	option 'autoshare' '1'
```

**风险**：`map to guest=Bad User` + `guest account=root` + `null passwords=yes` 组合起来 ≈ **任意无效/空口令的 SMB 客户端以 root 身份进入**；`server min protocol = NT1` 保留 SMB1（EternalBlue 等攻击面）；`smb encrypt = disabled` 无强制加密。注意工作区 AGENTS.md 里"旧机已设 `allow_legacy_protocols=0`"——**该设置在本机不存在**（这是刷机后的新实例）。

**建议动作**：
1. `/etc/config/samba` 置 `option 'enabled' '0'` + `stop` + `disable`（若无 NAS 共享需求，这是最直接的收敛）。
2. 若必须保留：`server min protocol = SMB2_10`（或 `SMB3`）、`smb encrypt = required`、`map to guest = never`、`null passwords = no`、`guest account = nobody`、`guest ok = no`，并用 `valid users` 限定。
3. 补 `smb ports = 445`（关闭 139）以减少 NetBIOS 广播面。

## C-4　全锥 NAT + 硬件流卸载 → **高**

**现状**：`firewall.@defaults[0].fullcone='1'`（IPv4 全锥）、`fullcone6='0'`；`flow_offloading='1'` + `flow_offloading_hw='1'`。

**证据**：
```
$ uci show firewall | grep -iE "fullcone|flow_offload"
firewall.@defaults[0].flow_offloading='1'
firewall.@defaults[0].flow_offloading_hw='1'
firewall.@defaults[0].fullcone='1'
firewall.@defaults[0].fullcone6='0'
$ nft list table inet fw4 | grep -iE "fullcone|flowtable|offload"
	meta nfproto ipv4 fullcone comment "!fw4: Handle wan IPv4 fullcone NAT dstnat traffic"
	meta nfproto ipv4 fullcone comment "!fw4: Handle wan IPv4 fullcone NAT srcnat traffic"
	flowtable ft { hook ingress priority filter; devices = { "lan1","lan2","lan3","lan4","pon0","ra0","rai0" }; flags offload }
```

**风险**：
- **全锥 NAT**：与对称/端口受限 NAT 不同，全锥允许**任意外部主机**向已建立的映射发起连接。本机在 CGNAT 后（`100.80.214.33`）尚有运营商级 NAT 兜底，但一旦换到公网 IPv4 或经 IPv6，全锥会让 LAN 内主机成为"可被扫描/主动连接"的目标，等价于隐式开放入站。
- **flow_offloading_hw=1**：工作区 AGENTS.md 明确记载"不要开 flow_offloading_hw（可能与 dae 的 eBPF 冲突）"。本机虽不是 dae，但 **nft redirect 到 :1234 的透明代理与流卸载存在语义冲突**：已建立的流被卸载到硬件后，后续按 `ip daddr @china` / gfwlist 的重判定不会再生效；且 `devices` 里包含 `ra0/rai0`（WiFi），**无线客户端的代理分流可能绕过 redirect**。

**建议动作**：
1. `fullcone` → `'0'`（若确需 P2P/游戏，另开明确的端口规则）。
2. `flow_offloading_hw` → `'0'`；`flow_offloading` 可保留 `'1'`（软件卸载）但需实测代理分流是否受影响（对已建流重定向规则失效是软件卸载的已知限制）。
3. 变更后必须 `firewall reload`（会短暂断网），建议在维护窗口做。

## C-5　DNS 污染未被挡住（chatgpt.com 等非 gfwlist 域名） → **高**

**现状**：dnsmasq 无 `noresolv`、无全局 `server=`，默认上游 = **运营商 DNS**（`210.22.70.225` / `210.22.70.3` / `2408:8026:480:112::6666`）。只有 gfwlist 内的 17804 个域名被指向 `127.0.0.1#5335`（dns2tcp → 8.8.4.4，走代理隧道）。**不在 gfwlist 的境外域名直接走运营商 DNS**。

**证据（chatgpt.com 实测被污染）**：
```
$ grep -c "chatgpt" /tmp/dnsmasq.cfg01411c.d/dnsmasq-ssrplus.d/gfw_list.conf
0                                   ← chatgpt.com 不在 gfwlist（只有 openai.com 在）
$ grep "server=/openai.com/" .../gfw_list.conf
server=/openai.com/127.0.0.1#5335

$ nslookup chatgpt.com 192.168.31.1
Address: 185.45.7.165                          ← Facebook 段 IP（污染）
Address: 2a03:2880:f10d:183:face:b00c:0:25de  ← Facebook IPv6（污染）

$ nslookup chatgpt.com 210.22.70.225
Address: 31.13.80.37                           ← 换一批污染 IP
$ nslookup chatgpt.com 210.22.70.3
Address: 128.242.240.155                       ← 再换一批

$ 真实答案（经代理走 DoH dns.google）
{"Status":0,...,"Answer":[{"name":"chatgpt.com.","type":1,"data":"104.18.32.47"},
                            {"name":"chatgpt.com.","type":1,"data":"172.64.155.209"}]}
```

对照：`www.google.com` 在 gfwlist 里 → 走 dns2tcp → 得到干净答案 `142.251.153.119`；`www.qq.com` → 走运营商 DNS → 得到正确国内 IP。

**风险**：
- **已确证污染**：chatgpt.com / www.microsoft.com 等在 gfwlist 覆盖不到或被过滤的域名，拿到的是 Facebook 段假 IP → 连接必然失败（表现为"域名污染型不可用"）。
- 运营商 DNS 同时可见**全部未命中 gfwlist 的域名查询明文**（隐私问题）。
- dns2tcp 上游 `8.8.4.4#53` 是**明文 UDP**，隧道内虽加密但代理↔Google 段明文。

**建议动作**：
1. 启用**全局**境外分流而非逐域名：把 `pdnsd_enable` 从 `1`（dns2tcp）切到 **`6`（chinadns-ng）**，配置 `chinadns_ng_proto='tls'`（DoT 到境外）+ `chinadns_forward='wan'`（国内走运营商），实现"国内域名走国内 DNS、境外域名走加密境外 DNS"的通用方案；或在 `global` 增加 `chinadns_forward` 让 chinadns-ng 做分流。
2. 至少把 `chatgpt.com`、`auth0.openai.com`、`cdn.oaistatic.com` 等常用但缺失的域名补进 gfwlist（黑名单式补洞治标不治本）。
3. 把 dns2tcp 上游从 `8.8.4.4:53` 换成 DoT（`tls://1.1.1.1:853` 之类）；`update.lua` / `subscribe.lua` 里的 `curl --insecure` 改为带证书校验。
4. 确认 `filter_aaaa` 的语义：dnsmasq 层 `filter_aaaa='0'` 只对**所有**域名生效，会连带砍掉国内 v6；建议保持 dnsmasq 层关闭、在 DNS 分流层按"境外/国内"分别处理。

## C-6　IPv6 分流缺口（境外 IPv6 完全不代理） → **高**

**现状**：`global.ipv6_support='0'` → ssr-plus 不做 IPv6 透明代理；nft 两条链首条规则均为 `meta nfproto ipv6 return`；而 LAN 侧 `odhcpd` 正常在发 RA、路由器持有全球 IPv6 `2408:820c:820a:a300::1/60`。

**证据**：
```
$ uci -q get shadowsocksr.@global[0].ipv6_support
0
$ nft list chain inet ss_spec ss_spec_prerouting | head -4
	chain ss_spec_prerouting {
		type nat hook prerouting priority filter; policy accept;
		meta nfproto ipv6 return          ← IPv6 直接放行
$ nft list chain inet ss_spec ss_spec_output | head -4
		meta nfproto ipv6 return          ← 同上
$ ip -6 addr show br-lan | grep inet6
	inet6 2408:820c:820a:a300::1/60 scope global dynamic noprefixroute
	inet6 fdae:8777:3859::1/60 scope global noprefixroute
$ ps w | grep odhcpd
2886 root 1788 S /usr/sbin/odhcpd
$ ip -6 route show | head -3
default from 2408:820c:8200:307f::/64 via fe80::6ee8:74ff:fedf:fc4d dev pppoe-wan ...
$ curl -6 -sS -o /dev/null -w "%{http_code}" --max-time 12 https://example.org
200                                       ← IPv6 直连境外成功（未代理）
$ ping6 -c2 2001:4860:4860::8888 → 2 packets received, 0% loss
```

同时，**境外 AAAA 只在 gfwlist 内被剥**（见 A4），不在 gfwlist 的境外域名仍返回真实 AAAA：

```
$ nslookup -type=AAAA example.org 192.168.31.1
Address: 2606:4700:10::ac42:9ded
Address: 2606:4700:10::6814:1a88
```

**风险**：客户端拿到境外 AAAA 后，会用 IPv6 **直连**境外（不经过 xray），意味着：
1. **代理被绕过**——IPv6 流量不走 REALITY 隧道，出站 IP 直接暴露家宽 IPv6（`2408:820c:...`），可被用于关联/追踪，也可访问被墙内容（若上游允许）。
2. **分流失效**——本应走代理的境外域名，部分连接走 IPv4 代理、部分走 IPv6 直连，形成出口分裂（与工作区 AGENTS.md 里 YouTube 403 那类"多出口"问题的同源风险）。
3. 当前 IPv6 TCP 到境外实际**可用**（curl -6 example.org = 200），说明这不是"v6 不通所以无所谓"的侥幸。

**建议动作**：
1. **方案 A（推荐，改动最小）**：保持 `ipv6_support=0`，但把 `dnsmasq.@dnsmasq[0].filter_aaaa` 设为 `'1'`，**全局剥掉 AAAA**，客户端自动回退 IPv4 走代理。代价是国内 IPv6 也被砍（与 AGENTS.md 记录的老方案副作用一致），需权衡——本机 `www.qq.com` 的 AAAA 是有效的。
2. **方案 B（分流正确）**：启用 `ipv6_support=1`（nftables 后端支持），让 ssr-plus 同时代理 IPv6；同时把 `chnroute6_url`（已配置 `https://raw.githubusercontent.com/1715173329/IPCIDR-CHINA/master/ipv6.txt`）与 `china6_ssr.txt`（18122 字节已就位）用起来 —— 需先验证 `china6_ssr.txt` 是否已按当前配置生成，以及 `ipv6.sh` 的 `ipv6_policy_route`（`ip -6 rule add fwmark 0x53535250 table 999` + `ip -6 route replace local ::/0 dev lo table 999`）在本机可用。
3. 中间路线：保留国内 AAAA，但**只对境外域名剥 AAAA**——需要把 AAAA 过滤下沉到"境外域名"这一层（chinadns-ng 的 `-N --filter-qtype 64,65` 参数正是干这个的，见 `start_dns()` 中 `pdnsd_enable=6` 分支）。

## C-7　dropbear 允许 root 密码登录 + MD5-crypt → **高**

**现状**：`PasswordAuth=on` + `RootPasswordAuth=on`，口令 `Qazswxdecf1` 的哈希为 `$1$`（MD5-crypt）。

**证据**：
```
$ cat /etc/config/dropbear
config dropbear
	option PasswordAuth 'on'
	option RootPasswordAuth 'on'
	option Port         '22'
$ ps w | grep dropbear
2454 root 1116 S /usr/sbin/dropbear -F -P /var/run/dropbear.1.pid -p 22 -K 300 -T 3
$ cut -d: -f2 /etc/shadow | cut -c1-3   → $1$  (MD5-crypt)
$ openssl passwd -1 -salt <salt> "Qazswxdecf1" → 与 shadow 完全一致
```

**风险**：`RootPasswordAuth=on` 允许 root 直接用口令登录；MD5-crypt 无内存硬化、无密钥拉伸参数，**离机爆破成本极低**（`/etc/shadow` 若因 C-2/C-3 的 FTP/SMB 泄露则直接失陷）。口令 `Qazswxdecf1` 同时是工作区记录的 VPS / daed / 青龙面板通用口令 —— 一处泄露横向全线。

**建议动作**：
1. `option RootPasswordAuth 'off'`（root 只允许密钥登录）。
2. 全网统一换强口令 + 升级哈希到 yescrypt（`passwd` 后 `grep root /etc/shadow` 应见 `$y$`）。
3. 部署 ed25519 密钥对，`~/.ssh/authorized_keys` 放好后再关密码。
4. 22 端口的可达性：wan zone input=REJECT 且无 redirect，**当前公网不可达**（见 C-9），但 LAN 内全开放。

## C-8　62 节点共用 1 个 UUID + 订阅抓取 `--insecure` → **中**

**现状**：62 个节点全部使用同一 `vmess_id`；订阅 URL 是 HTTPS 但抓取时 `--insecure`；UA 伪装成 `v2rayN/9.99`。

**证据**：
```
$ grep -h option.vmess_id /etc/config/shadowsocksr | sort -u | wc -l
1
$ grep -n "curl -sSL --http1.1" /usr/share/shadowsocksr/subscribe.lua
	'curl -sSL --http1.1 --connect-timeout 20 --max-time 30 --retry 3 -H "Accept-Encoding: identity" %s --insecure --location %s'
$ uci -q get shadowsocksr.@server_subscribe[0].user_agent
v2rayN/9.99
$ uci -q get shadowsocksr.@server_subscribe_item[0].url | cut -c1-30
https://hm.zmglqtdbkr.com/jiquan/...
```

**风险**：
- **共用 UUID**：机场/自建的所有 REALITY 节点共用同一凭据，任一节点泄露即波及全部 62 个；且 REALITY 服务端 `shortId` 各异但 UUID 相同，无法按节点隔离凭据。
- **`--insecure`**：TLS 证书不校验 → 中间人可**读取并篡改订阅内容**（拿到全部节点 UUID/服务器地址），或替换 `update.lua` 拉取的 gfwlist / chnroute（把 chnroute 改小 → 更多境外流量被代理；改大 → 境外流量直连泄漏）。
- **UA `v2rayN/9.99`**：明显的客户端指纹，便于机场侧识别。

**建议动作**：
1. 去掉 `--insecure`（订阅服务器若无合法证书链，改用 `--cacert` 指定自签 CA）。
2. 若节点由服务商统一下发，UUID 共用无法在本机改；自建节点则应**逐节点独立 UUID**。
3. `user_agent` 改成不易识别的值（如浏览器 UA）。

## C-9　UPnP/xupnpd init 自启 + 无端口转发 + 全锥 NAT 的组合 → **中**

**现状**：`/etc/rc.d/` 里有 `S94miniupnpd` 和 `S50xupnpd`（**开机自启**），虽 `upnpd`/`xupnpd` 的 config 里 `enabled=0` 导致启动即退出；`firewall` 无任何 `config redirect`。

**证据**：
```
$ ls -la /etc/rc.d/ | grep -E "miniupnpd|xupnpd"
lrwxrwxrwx 1 root root 19 S94miniupnpd -> ../init.d/miniupnpd
lrwxrwxrwx 1 root root 16 S50xupnpd  -> ../init.d/xupnpd
$ cat /etc/config/upnpd
config upnpd config
	option enabled		0
	option enable_natpmp	1
	option enable_upnp	1
	option secure_mode	1
	option port		5000
	option internal_iface	lan
config perm_rule
	option action allow / ext_ports 1024-65535 / int_ports 1024-65535
config perm_rule
	option action deny / ext_ports 0-65535
$ ps w | grep -iE "miniupnpd|xupnpd"     → (无进程)
$ uci show firewall | grep -i redirect  → (无输出)
$ nft list table inet fw4 | grep -i dnat
	ct status dnat accept comment "!fw4: Accept port redirections"
	ct status dnat accept comment "!fw4: Accept port forwards"
```

**风险**：
- 当前 **无实际 UPnP 进程、无端口转发**，公网入站被 `input REJECT` + `reject_from_wan` 挡住 —— **这是当前最好的一面**。
- 但 `miniupnpd`/`xupnpd` 的 init **开机自启**，任何一次 LuCI 里误点"启用 UPnP"或包升级后 config 被改写，即可在**没有任何防火墙规则**的情况下开洞（UPnP 会自动写 redirect 规则）。`enable_natpmp=1` 也还在（NAT-PMP 与 UPnP 一样能自动映射端口）。
- 全锥 NAT（C-4）叠加后，一旦有映射，**任意外部主机都能主动连入**（全锥语义），不再是"仅对端可连"。

**建议动作**：
1. `xupnpd disable`、`miniupnpd disable`（**关掉 init 自启**），并在 LuCI 里保持 `enabled=0`。
2. 把 `upnpd` 的 `enable_natpmp` 也置 `0`。
3. 若需要远程访问，改用 **VPN 回连**（wireguard/openvpn 拨入）或 IPv6 + 强认证服务，**不要**用 UPnP/端口转发。

## C-10　dnsmasq 监听 WAN 侧地址 + IPv6 DNS 全开 → **中**

**现状**：dnsmasq 绑定 `100.80.214.33:53`（PPPoE WAN 侧 CGNAT 地址）、`2408:820c:820a:a300::1:53`、`fdae:8777:3859::1:53`、以及 `2408:820c:8200:307f:ed9b:500e:4116:2905:53`（另一个 PD 前缀）。

**证据**：
```
$ netstat -tulnp | grep dnsmasq
tcp 0 0 127.0.0.1:53          LISTEN 10193/dnsmasq
tcp 0 0 192.168.31.1:53       LISTEN 10193/dnsmasq
tcp 0 0 100.80.214.33:53      LISTEN 10193/dnsmasq
tcp 0 0 2408:820c:820a:a300::1:53       LISTEN 10193/dnsmasq
tcp 0 0 2408:820c:8200:307f:ed9b:500e:4116:2905:53  LISTEN 10193/dnsmasq
tcp 0 0 fdae:8777:3859::1:53            LISTEN 10193/dnsmasq
udp 0 0 0.0.0.0:67           LISTEN 10193/dnsmasq
```

**风险**：
- `100.80.214.33` 是 CGNAT 共享地址段（100.64.0.0/10），**同 PON 的其他用户理论上可直连该地址**尝试 DNS 反射攻击（递归解析器放大）。dnsmasq 有 `localservice '1'`（仅服务本地网段），会拒绝对端查询，实际风险被大幅限制。
- **IPv6 侧无 `localservice` 保护时风险更高**：`2408:820c:...` 是**全球可路由**的 IPv6，dnsmasq 监听在它上面。虽然 `wan` zone `input REJECT` + `reject_from_wan` 会在防火墙层挡掉外部进入的 53 端口，但 DNS over IPv6 若被放行会成为开放递归器。
- `option localservice '1'` 已设 ✅，但 IPv6 前缀有两个（`8200:307f:...` 和 `820a:a300:...`），`rebind_protection`/`localise_queries` 已在。

**建议动作**：
1. 确认 dnsmasq 仍有 `option localservice '1'`（已确认有）。
2. 在 wan zone 显式加一条 `reject` 规则针对 UDP/TCP 53（虽 `input REJECT` 已覆盖，冗余一层更保险，尤其 IPv6）。
3. `option localservice` 对 IPv6 的行为在 OpenWrt 25.12 上有时不覆盖全局地址 → 建议额外验证（用外部主机 `dig @2408:820c:820a:a300::1` 实测）。

## C-11　ssr-rules 每 300s 重写持久化文件 + ssr-switch 667s 轮询 → **中**

**现状**：见 A6 详解。核心结论：**667s 轮询本身不造成周期性断流**（从未触发切换），但 ssr-rules 的 300s 自检会**周期性重写 192KB 的 nftables 持久化文件**。

**证据**：
```
$ tail -40 /var/log/ssrplus.log
2026-10-21 21:07:07: ssr-rules: Using nftables
2026-10-21 21:12:08: ssr-rules: Using nftables
...（严格 5 分钟一次，持续到 23:57:28）
$ logread | grep -i "Switch to"
(无输出)   ← ssr-switch 从未切换节点
$ ps w | grep "sleep 0000"
26390 root 1332 S sleep 0000667s
$ grep -n "AUTO_UPDATE_INTERVAL" /usr/bin/ssr-rules
	AUTO_UPDATE_INTERVAL=300  # auto-update check interval (seconds), 0 means disable
$ ls -la /usr/share/nftables.d/ruleset-post/
-rw-r--r-- 1 root root 192570 99-shadowsocksr.nft
```

**风险**：
1. **flash 写放大**：每 5 分钟 `rm -f` + 重写 192KB。`-P`（`force_update_persistence`）走的是"强制重建"分支，**不走 `compare_rules` 的跳过逻辑**——只有 `-C` 自检通过时才不触发，但 `-C` 的判定只看"表和基本规则是否存在"，规则内容变化时仍会重写。
2. **窗口期风险**：`rm -f` 与重写之间存在短暂空窗，若此刻触发 `firewall reload`，ssr-plus 的透明代理规则会丢失 → **全量流量直连泄漏**。
3. `ssr-switch` 的 `check_direct_probe()` 因路由器自身出口也被 `ss_spec_output` 代理，实际探测的是"代理是否通"而非"直连是否通" —— 逻辑偏差，导致该守护进程几乎永远不会切换（实测也印证了：从未切换）。

**建议动作**：
1. `AUTO_UPDATE_INTERVAL=0`（代码支持，注释明确写 "0 means disable"）或调大到 3600。
2. 修 `force_update_persistence` 使其在非 FORCE 场景走 `compare_rules` 短路（上游已具备该分支，是 `-P` 强制路径绕过了它）。
3. 若不需要自动故障切换：`global.enable_switch='0'`（本次审计确认 667s 轮询从未生效，关闭零损失）。

## C-12　订阅更新每天 02:00 无条件重启代理 → **中**

**现状**：cron `0 2 * * * /usr/share/shadowsocksr/ssrplusupdate.sh` → `subscribe.lua` 末尾**无条件**执行 `/etc/init.d/shadowsocksr restart`（无论节点列表是否变化）。

**证据**：
```
$ crontab -l
0 2 * * * /usr/share/shadowsocksr/ssrplusupdate.sh >/var/log/ssrplus.log
$ sed -n '2985,2995p' /usr/share/shadowsocksr/subscribe.lua
	else
		log('维持当前主服务器节点。')
		luci.sys.call("/etc/init.d/" .. name .. " restart > /dev/null 2>&1 &")
	end
```

**风险**：每天 02:00 一次**全量断流**（xray 重启 + nft 规则重建 + dnsmasq 重启 + `uci commit shadowsocksr`），持续数秒到数十秒。若家中设备在凌晨有定时任务（备份、同步、监控）会失败。

**建议动作**：
1. 改为**内容变更才重启**：在 `subscribe.lua` 中比较新旧节点 md5（`read_old_mdx` / `new_md5` 机制已存在），仅在 md5 变化时 restart。
2. 或改 cron 到低峰且避开关键任务；或临时把 `config_auto_update_mode` 设为 `1`（loop 模式按 `config_update_interval` 节流，变更才更新）。
3. 顺带确认 `update.lua` 拉取 gfwlist/chnroute 后是否也触发规则重载（当前 `update.lua` 内无 `restart` 调用，只写文件 + `chinaipset.sh` 重建 ipset，影响面较小）。

## C-13　openclash 残留 + firewall include 指向缺失文件 → **中**

**现状**：`/etc/openclash` 占 10.8MB，`openclash.config.enable='0'`，无进程，但 `/etc/rc.d/S99openclash` 开机自启；`/etc/config/firewall` 里有 `config include 'openclash'` 指向 **`/var/etc/openclash.include`（不存在）**。

**证据**：
```
$ du -sh /etc/openclash
10.8M	/etc/openclash
$ ls -la /etc/openclash/core/
（空目录）
$ uci show openclash | grep enable
openclash.config.enable='0'
$ ps w | grep -iE "openclash|mihomo|clash"
(无输出)
$ ls -la /var/etc/openclash.include
ls: /var/etc/openclash.include: No such file or directory
$ ls /etc/rc.d/ | grep openclash
K15openclash  S99openclash
$ ls /etc/openclash/
Country.mmdb  GeoSite.dat  china_ip6_route.ipset  china_ip_route.ipset  config  core  custom  history  overwrite  proxy_provider  rule_provider
```

**风险**：
1. **firewall include 悬空**：每次 `firewall reload` 时 fw4 会尝试执行 `/var/etc/openclash.include` → 该文件不存在 → fw4 可能报 "Could not open file" 并**中止整个防火墙重载**（导致规则未刷新）。需实测 fw4 版本行为，但这是明确的配置不一致。
2. **开机自启的 openclash init** 虽 `enable=0` 会早退，但仍有残余执行风险（且 `/etc/openclash/config` 可能含历史订阅/节点凭据）。
3. 10.8MB 占用（含 GeoSite.dat / Country.mmdb / ipset），在本机 overlay 上是纯浪费。

**建议动作**：
1. 从 `/etc/config/firewall` 删除 `config include 'openclash'` 段（**改配置需用户确认**，本次只读未动）。
2. `opkg remove luci-app-openclash`（或至少 `rm -rf /etc/openclash` + `opkg remove` 相关包）释放空间。
3. 同类检查：`/etc/ssrplus/mosdns-config.yaml`、`dnsproxy_dns.list`、`clash/` 也是未启用的残留。

## C-14　TR069 / 运营商管理通道 —— **无残留（低，正面）**

**现状**：全盘 grep 无任何 TR069/CWMP/ACS 配置、守护或日志。

**证据**：
```
$ grep -rIl -i -E "tr069|cwmp|acs_url|acsusername|acs_password|tr-069|easycwmp" /etc
(无输出)
$ ls /etc/init.d/ | grep -iE "tr069|cwmp|acs|omci"
(无输出)
$ logread | grep -iE "tr069|cwmp|acs"
(无输出)
$ grep -rn -i "vlan" /etc/config/
(无 vlan 28 配置)
```

**风险**：原厂 CT 的 TR069（CWMP）自动管理通道在刷 QWRT 后**已消失**，这是正面结论。

**残留关注点**：`/etc/config/pon` 仍保留 `option operator 'ctc'` + `operator 'ctc'` 的 OAM/CTC 标识与 LOID，**这属于 ONT 注册必需**（不改则 PON 可能注册失败），且 TR069 承载在 VLAN 28 上而本机无 VLAN 配置。**建议在运维侧（联通侧）确认该 ONT 的 TR069 会话/ VLAN 28 是否仍在被运营商标配**——这是运营商侧的事，本机配置层面已无残留。

**建议动作**：向联通确认 ONT 的远程管理策略是否已关闭（要求解除 VLAN 28 的 TR069 绑定或停止下发），本机侧无需改动。

## C-15　无 `/etc/firewall.user`，自定义 nft 仅 ss_spec 表 —— **低（正面）**

**现状**：无 `/etc/firewall.user`；唯一的自定义 nft 持久化是 ssr-plus 自己的 `99-shadowsocksr.nft`（192KB），以及 `inet ss_spec` / `ip ss_spec_mangle` 两张表。

**证据**：
```
$ ls -la /etc/firewall.user
ls: /etc/firewall.user: No such file or directory
$ ls -la /usr/share/nftables.d/ruleset-post/
-rw-r--r-- 1 root root 192570 99-shadowsocksr.nft
$ nft list tables
table inet fw4
table inet ss_spec
table ip ss_spec_mangle
```

**风险**：低。无隐藏的额外放行规则；fw4 规则集本身（`inet fw4`）只有标准 default/zone/rule，无第三方注入（除 C-13 的悬空 include）。

**建议动作**：保持现状。唯一要管的是 C-11 的 `99-shadowsocksr.nft` 重写频率。

---

## 附：本次审计"未做"事项（保持只读）

按要求，以下动作**均未执行**，仅作为建议列出：
- 未执行任何 `uci set` / `uci commit` / `uci delete`
- 未执行 `/etc/init.d/* start|stop|restart|enable|disable`
- 未修改 `/etc/config/*`、`/etc/shadow`、`/etc/passwd`、防火墙规则
- 未重启路由器、未 reload 防火墙
- 未向路由器写入任何文件（所有采集命令均为只读；`ssrplusupdate.sh` 的 cron 由系统自身调度，非本次触发）
- 本次唯一在路由器上产生的写操作是 **openssl passwd 本地计算**（纯计算，不落盘）与 **netstat/nft/ss 等只读查询**
