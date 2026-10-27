# QWRT R26.10.25 升级 + OpenClash→nikki 迁移完成报告

> 日期：2026-10-26 18:47 ｜ 机器：HG5585F-CT（主路由，AN7581，410MB RAM）
> 前序：`reports/QWRT-R26.10.25-升级评估-20261026.md`（升级前评估）

---

## 0. 一句话结论

**升级成功，代理栈已从 OpenClash 切换到 nikki（原生 mihomo），全屋代理恢复正常，且可用内存从 39MB 提升到 119MB。**
唯一遗留是"乌龟"机场订阅 403（升级前就 403，非本次引入）。

---

## 1. 升级过程中的两个坑（已解决，记录备查）

### 坑 1：第一次升级失败 = tmpfs OOM，不是固件问题

- 现象：点"继续"后无反应，版本仍 R26.10.21、uptime 未清零。
- 证据：`/tmp` 留有 `firmware.bin`(55MB)+`sysupgrade.tgz`(17MB)+`sysupgrade.meta` → sysupgrade 已启动；
  dmesg 两次 OOM：`Out of memory: Killed process (clash) total-vm:1389228kB`，且 `sysupgrade` 也在被杀名单。
- 根因：**`/tmp` 是 tmpfs（吃 RAM）**，当时同时存在：LuCI 上传的固件 55MB + 配置备份 17MB +
  我上午遗留的 `QWRT-R26.10.25.itb`(55MB) 与 `ct-config-R26.10.21.tar.gz`(17MB) + OpenClash 核心 ~100MB，
  410MB 机器直接爆内存。
- 处置：删 `/tmp` 遗留文件、停 OpenClash（可用内存 39MB → **149MB**），改用命令行
  `sysupgrade -v /tmp/firmware.bin` 重刷，一次成功。
- **教训：这台机器升级前必须保证 `/tmp` 干净 + OpenClash 已停。**

### 坑 2：新固件不带 geodata，nikki 首次启动会卡在下载

- mihomo 启动时根据规则里的 `GEOSITE,...` 去下载 `GeoSite.dat`（GitHub），**此刻本机还没代理 → 死循环超时**，
  校验报 `can't initial GeoSite: context deadline exceeded`。
- 处置：把 QWRT 旧固件里的 `GeoSite.dat`(9.93MB) + `Country.mmdb`(200KB) 放到 `/etc/nikki/run/` 下，
  再 `mihomo -d /etc/nikki/run -t` 校验通过（2.6s，所有 GeoSite 规则加载成功）。
- 已加入 keep：`/etc/nikki/`（含 geodata 与 profile），下次升级不丢。

---

## 2. 升级后状态（实测）

| 项 | 升级前 | 升级后 |
|---|---|---|
| 版本 | R26.10.21 | **R26.10.25**（OpenWrt 25.12.3 r7953） |
| 内核 | 5.4.302 | 5.4.302（未变；dae 仍不可用） |
| PPPoE | 100.66.213.83 | 100.92.248.69（重拨，正常） |
| lan1 | 2500 Mbps | **2500** ✅ |
| PON | operational | **operational / service_ready=1** ✅ |
| WiFi | bernard / bernard_5G | **原样保留**，ra0 24dBm/HE20 ✅ |
| 可用内存 | **39 MB** | **119 MB** ✅ |
| overlay 占用 | 19.5 MB | **11.2 MB**（删 OpenClash 后） |
| nft_tproxy | 无 | **nft_tproxy.ko 已加载** ✅ |
| 代理栈 | OpenClash + Ruby（RSS 106MB） | **nikki + mihomo 1.19.32**（RSS 88MB，无 Ruby） |

---

## 3. nikki 配置（本次迁移的核心）

### 3.1 配置方式：file profile

```sh
uci set nikki.config.enabled='1'
uci set nikki.config.profile='file:openclash-20261022.yaml'
```
profile 位置：`/etc/nikki/profiles/openclash-20261022.yaml`（由现网 OpenClash YAML 自动转换）。
nikki 会把它复制到 `/etc/nikki/run/config.yaml`，mihomo 以 `-d /etc/nikki/run` 启动。

### 3.2 转换时做的 3 处适配（`tools/make_nikki_profile.py`）

| 适配 | 原因 |
|---|---|
| provider 路径改绝对路径 `/etc/nikki/run/providers/{proxy,rule}/` | mihomo 工作目录变成 `/etc/nikki/run`，相对路径会错位 |
| 删除 `port/socks-port/mixed-port/redir-port/tproxy-port/external-controller/secret/allow-lan/tun` | 这些由 nikki 的 ucode mixin 统一注入，profile 里再写会重复监听 |
| 关闭 `nikki.mixin.*` 的 9 个 overwrite 开关 | 避免 nikki 删掉我 profile 里的 `dns.nameserver` / `fake-ip-filter` / `sniffer` |

保留了：3 个 proxy-provider、2 个自建节点、19 个 proxy-group、4 个 rule-provider、44 条 rules、完整 DNS（fake-ip + respect-rules + nameserver-policy）。

### 3.3 代理模式（这次的关键升级）

```sh
uci set nikki.proxy.tcp_mode='redirect'
uci set nikki.proxy.udp_mode='tproxy'    # 宿主机内核已补 nft_tproxy
```
- 之前 OpenClash 只能 fake-IP + TUN（UDP 受限）；
- 现在 UDP 走 **TPROXY**，是内核态转发，比 TUN 省内存、UDP 更可靠。

### 3.4 内存护栏

```sh
uci set nikki.procd.env_go_mem_limit='80MiB'
uci set nikki.procd.env_go_max_procs='2'
```
410MB 机器上给 mihomo 一个上限，避免历史 OOM 重演（旧的 OpenClash 双实例 OOM 就是没上限）。

### 3.5 geodata

- `/etc/nikki/run/GeoSite.dat`（9.93MB，取自 QWRT 旧固件）
- `/etc/nikki/run/Country.mmdb`（200KB）
- 两者已随 `/etc/nikki/` 进 sysupgrade keep。

---

## 4. 实测验证（全部通过）

| 测试 | 结果 |
|---|---|
| **国外出口** | `89.185.25.210 / Hong Kong / HK` ✅（走代理） |
| **国内出口** | `223.167.151.129 中国上海联通` ✅（直连未代理） |
| YouTube `generate_204` | **204** ✅ |
| Google `generate_204` | **204** ✅ |
| GitHub | **200** ✅ |
| OpenAI API | **401**（可达）✅ |
| DNS 国外（fake-ip） | `198.18.0.21` / `2001:2::12` ✅ |
| DNS 国内 | 真实阿里 IP（未 fake-ip）✅ |
| nft 表 | `inet fw4` + **`inet nikki`** ✅（无残留 guard） |
| 启动日志 | `[Proxy] Hijack successful` ✅ |
| 配置校验 | `[Profile] Test passed` ✅ |
| RSS / available | **88 MB / 119 MB** ✅ |

**唯一错误**（升级前既有，非本次引入）：
```
level=error msg="initial proxy provider 乌龟 error: 403 Forbidden"
```
乌龟机场订阅被锁（`Subscribe refresh is locked`），需要去机场后台解锁，或从 provider 列表移除。

---

## 5. 本次清理（"没用的删掉"）

| 清理项 | 结果 |
|---|---|
| `/etc/openclash`（24.9MB）+ `/etc/config/openclash` | **已删除**（PC 上有完整备份） |
| `openclash-v6-guard.sh` / hotplug guard | 已随升级消失（升级前已从 keep 移除，避免了 fake-IP 黑洞） |
| `ocmon.sh` cron 行 | 已删除（无 OpenClash 可监控） |
| 停用服务（26 个） | 3proxy、microsocks、vlmcsd、vsftpd、xupnpd、samba、miniupnpd、msd_lite、shadowsocksr、telnetd、usbmuxd、sms_forwarder、ubus-at-daemon、qmodem×(7)、modemdata、zerotier、openvpn、arpbind、autoreboot、luci-client-history |
| 启用服务 | 从 50+ 精简到 **38 个**（保留 PON/网络/WiFi/防火墙/DDNS/nikki/cron 等必需品） |
| `/tmp` 清理 | 固件、备份包、旧日志全部清除 |

**保留未动的**：`iptv`（配置里 enabled=0，但服务仍启用）、`ddns`、`ipv6set`、`cpufreq`、`mtwifi*`、`pon*`、`packet_steering`、`airoha_fan`。

---

## 6. 回滚路径（如需）

1. **回滚固件**：`sysupgrade -v` 刷回 `QWRT-R26.10.21-…-ct-squashfs-sysupgrade.itb`（D 盘有两份），保留配置。
2. **回滚代理**：`/etc/nikki/profiles/` 保留 profile；`uci set nikki.config.enabled='0'` 即可停用。
3. **OpenClash 配置**：完整备份在 `backups/openclash-20261022/final/` + `tmp/live-openclash-20261022.yaml` + `tmp/ct-config-R26.10.21.tar.gz`。
4. **紧急**：U-Boot HTTP recovery（`192.168.0.1`，网线插 **LAN2/3/4**，2.5G 口在 U-Boot 阶段不通）。

---

## 7. 后续建议

1. **乌龟订阅**：去机场后台解锁，或从 `proxy-providers` 删掉（现在它每次重载都报错，虽不影响使用）。
2. **观察 24h**：`free` / `grep level=error /var/log/nikki/core.log`，确认 RSS 稳定在 90MB 内、无 OOM。
3. **可选**：把 `luci-app-nikki` 面板加个书签（`服务 → nikki`）；`:9090` 的 zashboard 也可用。
4. **CU 实验机**：目前离线（网线可能拔了）。dae 那套配置都在，需要时接回即可，不冲突。

---

## 附：关键文件位置

| 内容 | 位置 |
|---|---|
| nikki profile | `/etc/nikki/profiles/openclash-20261022.yaml` |
| 运行时配置 | `/etc/nikki/run/config.yaml` |
| geodata | `/etc/nikki/run/{GeoSite.dat,Country.mmdb}` |
| 日志 | `/var/log/nikki/{app.log,core.log}` |
| 转换脚本 | `tools/make_nikki_profile.py` |
| 升级前配置备份 | `tmp/ct-config-R26.10.21.tar.gz`（PC） |
| 现网 YAML 备份 | `tmp/live-openclash-20261022.yaml`（PC） |
