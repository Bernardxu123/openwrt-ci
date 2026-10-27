# 08 · 刷 QWRT R26.10.21（CT 版）主线

> 目标机：**HG5585F-CT（电信版，lan1=2.5G）** ｜ 目标固件：**QWRT R26.10.21 CT**（`物料/可选-QWRT/`，42,201,767 B，sha256 `8592e57a…a29f049`）；旧版 R26.10.18（42,152,775 B，sha256 `5053531f…7450ae53`）保留作回滚
> 本文是 **QWRT 主线**；`01-刷机流程.md` 是 ponwrt 主线。刷前阶段（拿 root、备份、factory）两条线完全一样。
> 结论先给：**QWRT 能刷、有它的好处，但它不是 ponwrt 的“升级版”**——老内核、无 Passwall、默认网络形态不同，先看第 0 节取舍。

> ## ⭐ 2026-10-21 19:36 二次实刷：R26.10.21 + PON 已通
>
> - **R26.10.21 修复了 R26.10.18 的 PON OAM 兼容问题**：新 `airoha-pond` sha256 `d6974f7b…`（旧 `42001c73…`，同尺寸 592,315 B 重编）；旧版会把 OAM 帧尾 FCS 当 TLV、且不认 11 字节 CTC 版本选择，卡在 `version-offered`；新版实测 `parse_errors: 0`、`ctc_version: 0x30`、`authentication_status: accepted`。
> - **新固件默认 `pon` 配置缺 `operator='ctc'`**（`S18pon` 会选 OMCI，PON 线保持 `stopped`）——必须补：
>   ```sh
>   uci set pon.line0_oam.operator='ctc'
>   uci set pon.line0_oam.loid='000000000000000014509791'
>   uci set pon.line0.serial_number='46485454c1c6acaa'
>   uci commit pon
>   ```
> - **PON 身份按现网 CU 光猫克隆**：`pon0` MAC `D0:69:FF:16:32:80` 由 `/etc/init.d/pon-macclone`（START=17，早于 `pon` 的 18）开机设置；UCI PON SN 用 CU 的 `46485454c1c6acaa`。只改 MAC 时 OLT 只做 IEEE 发现、不发 CTC；MAC+SN 一起改才 `accepted`。
> - 实测结果：PON `operational` / `service_ready: true`；`pon0.995` PPPoE 在线（IPv4 动态 CGNAT，最后一次 `100.80.214.33`；出口公网 `223.166.243.51`）；IPv6 PD 动态（最后一次 `2408:820c:820a:a300::/60`），PC 有全球 v6；LAN `192.168.31.1`；2.5G lan1 实测 `2500Mb/s`。
> - WiFi（用户现网）：`bernard` ch6 HE20 / `bernard_5G` **ch36 HE160**，WPA2 `18501760081`；客户端实测 RX/TX 均 160MHz。
> - ⚠️ 不要同时让原 CU 光猫和这台 CT 在同一条 PON 上（同 MAC/SN）；**不需要整包刷 CU 1 MiB factory**（会搬走单机 PON 校准/WiFi EEPROM），只克隆 MAC+SN 即可。

> ## ✅ 2026-10-21 实刷结果（本机已刷成功）
>
> 本机（MAC `70:D5:1E:06:9C:78`，PON SN `FHTTC123E98A`）已按本文完成：
>
> 1. Telnet `su` 拿到 root（**未拆机/未用串口**）→ stock2ubi `:3333` → 17 分区备份；
> 2. `fiberhome-factory.exe` 转出 `factory-1m.bin`，**五项校验全过**；
> 3. stock2ubi `/api/flash` 写 BL2+FIP → U-Boot `192.168.0.1`；
> 4. **Rebuild UBI → Write fip → Restore board data → 刷 QWRT → Boot** 全部成功；
> 5. 首启已改：root 口令 `Qazswxdecf1`、WiFi `ct-qwrt`/`ct-qwrt_5G` WPA2、PON `epon-10g-1g`/`ge_ports=4`/LOID、WAN `pon0.995` PPPoE、`lan1` 并入 `br-lan`；
> 6. 重启一次验证配置全部持久化；日志确认 **`serial_number: 46485454c123e98a`**（从 board data 正确读取）。
>
> **尚未验证**：接光纤后的 PON 注册 / PPPoE（当前 `optical signal absent`）。
> 详细时间线与参数见 `数据模板/刷机记录.md`，分区备份见 `备份/原厂-20261021/`。

---

## 0. 先决定：QWRT 还是 ponwrt？

| 维度 | **QWRT R26.10.18 CT** | ponwrt v2026.10.18 CT |
|---|---|---|
| 内核 | **5.4.302（Airoha BSP）** | 6.18.55（mainline） |
| WiFi 驱动 | **闭源 `mt7916_ap.ko` + `mtwifi`**（`ra0/rai0`） | 开源 `mt7915e`（`phy0-ap0`） |
| WiFi 稳定性 | 闭源驱动通常更稳、功能更全（QWRT 的主要卖点） | 上游 mt76，CU 机实测可用；热区注册报错属无害 |
| 2.5G 口 | `lan1` 默认是 **WAN**（DHCP 客户端） | `lan1` 是 LAN，`br-lan` 成员 |
| 默认 LAN | **192.168.1.1** | 192.168.31.1 |
| 默认账号 | **root / `password`**；Telnet 23 **默认开**；SSH 22 开（**本机已改为 `Qazswxdecf1`**） | root 空密码；SSH 开；Telnet 关 |
| 代理 | **无 Passwall**；自带 openclash / xray 二进制 / SSR-Plus 配置 | **自带 Passwall**（xray/sing-box/hysteria/geoview/chinadns） |
| 包管理 | opkg，但首启脚本会把 feeds 改成 **ImmortalWrt 24.10.6**（与 25.12.3 镜像不匹配） | apk，需要自行切镜像 |
| PR #34（GPY211C 暖重启修复） | **没有**（DTB 仍是旧写法 `ethernet-phy-ieee802.3-c45`，deassert 800ms） | **有**（`ethernet-phy-id67c9.de10`） |
| reset 键 DTB | **GPIO0**（与实际 GPIO35 不符） | GPIO35 |
| 签名 | 有 usign/ucert（`Local build key`） | 无 usign |
| 适合谁 | 想要**闭源 WiFi/2.5G 当 AP 或主路由**、能接受没有 Passwall | 想要**现成 Passwall 分流**、接受开源 WiFi |

**一句话建议**：
- **WiFi/2.5G 优先、代理可以另想办法** → 刷 QWRT（本文）。
- **代理/分流优先、WiFi 够用就行** → 留 ponwrt（`01`）。
- 两个都想要：先刷 QWRT 验证 WiFi/2.5G，再决定是否回 ponwrt；**不要指望在 QWRT 上直接复刻 Passwall 配置**（feeds 不匹配，见 §8）。

---

## 1. 物料与前提

### 1.1 必须

| 物料 | 路径 | 说明 |
|---|---|---|
| QWRT CT sysupgrade（当前） | `物料/可选-QWRT/QWRT-R26.10.21-…-ct-squashfs-sysupgrade.itb` | 42,201,767 B；**PON OAM 修复版**（10-21 构建）；sha256 `8592e57a…`；**只能用 CT 包** |
| QWRT CT sysupgrade（回滚） | `物料/可选-QWRT/QWRT-R26.10.18-…-ct-squashfs-sysupgrade.itb` | 42,152,775 B；sha256 `5053531f…`；旧版 PON OAM 不兼容，仅回滚用 |
| CT 引导三件套 | `物料/引导/` | firstblock / preloader / fip，与共享资料里的**逐字节相同** |
| `an758x-stock2ubi` | `物料/工具/` | 原厂系统里跑，起 `:3333` |
| `fiberhome-factory.exe` | `物料/工具/` | `mtd13` 3 MiB → 1 MiB |
| CT 自己的 `factory-1m.bin` | 现场生成 | **必需**：PON 校准 + WiFi EEPROM（QWRT 闭源 WiFi 也从 `factory 0x1000` 读 4 KiB EEPROM，首两字节必须 `16 79`） |

### 1.2 可选 / 共享资料

| 物料 | 状态 | 用途 |
|---|---|---|
| `下载资料/ftp/tftpd64.exe` | 可选 | 若光猫 `wget` 取 stock2ubi 失败，用 TFTP 替代（静态核对为官方 4.64 原样包；仍建议从官方源重取比对哈希） |
| `下载资料/HG5585F-CT-V2一键开Telnet.exe` | **可用，但要按隔离流程** | PyInstaller 打包的 `/fh_tool/api` 封装：`GetDevInfo` + `TelnetEnable`（运行时）+ Telnet `cfg_cmd` 持久化。**静态无恶意**（无扫描/下载/注册表/提权/捆绑/外联），但无签名、作者匿名、会改持久化配置；详见 `分析/共享资料评估.md` |
| `下载资料/uboot/` | 与本地物料重复 | 可当第二份副本交叉校验，无需使用 |
| `下载资料/ftp/an758x-stock2ubi` | 与本地物料重复 | 同上 |

> 共享资料里**没有 QWRT 固件本体**；QWRT 包来自工作区已有的 `光猫-HG5585F/QWRT-R26.10.18-…-ct-…itb`（已复制进本包）。

### 1.3 ⭐ 拿 Telnet 的最快路径（不用拆机）

共享工具暴露了两个关键事实（静态证据，见 `分析/共享资料评估.md`）：

- **CT V2 的 Web/API 端口默认是 `8080`**（不是 80）；
- **CT V2 的 Telnet 默认账号是 `telnetadmin`，口令是 `'FH-nE7jA%5m' + MAC 后六位`**；
- 工具自带硬版本闸门 `hardwareversion=V4.2.0` / `softwareversion=24FHW45000`，**不匹配就中止**，不会乱改。

**推荐做法（可审计，优先）**：用本包脚本，不依赖第三方 EXE：

```powershell
# 只读探测（自动从 web_get_brmad 读 MAC；默认 8080→80）
python .\脚本\fhtool-ct.py 192.168.1.1

# 开运行时 Telnet（不持久化，重启失效）
python .\脚本\fhtool-ct.py 192.168.1.1 --telnet-on
```

然后 Telnet 登录（候选顺序）：

```
telnetadmin / FH-nE7jA%5m + MAC 后六位     ← CT V2 默认
admin       / Fh@ + MAC 后六位            ← CU/旧固件
```

如果进去就是 **root**（`id` 显示 uid=0），直接跳到 §2 的 stock2ubi 备份，**完全不需要拆机/串口**。
如果只是 opuser：再试 `su`（候选同上），不行就回 `01` 阶段 2 的串口路线。

**如果坚持用共享 EXE**（例如想看它的持久化档）：

1. `HG5585F-CT-V2一键开Telnet.exe --host 192.168.1.1 --web-port 8080 --probe` —— 只读，到版本校验就停；
2. 确认版本是 `V4.2.0 / 24FHW45000` 后，再考虑 `--runtime-only`（只开运行时，不写 `cfg_cmd`）；
3. 默认第 3 档才会用 `cfg_cmd set …X_CT-COM_ServiceManage(.Lan).TelnetEnable 1` 做持久化——**会改设备配置**，非必要不用；
4. 全程 PC 与光猫**单线直连**、关 WiFi/其他网卡、Wireshark 只看 `192.168.1.1`、跑前先做 `03` 的备份；跑完立刻关 Telnet/改口令/断直连。

> 工具的报告与重建源码：`分析/共享资料评估.md`、`分析/telnet-tool/`。结论：**能用，但不建议在主力机双击**；优先用 `脚本/fhtool-ct.py`。

### 1.3 前置

- 按 `03-身份采集与备份.md` 完成：17 分区备份 + `factory-1m.bin` 五项校验 + `identity-ct.json`。
- 按 `01` 阶段 4 写好 CT 的 U-Boot（firstblock + fip），能进 `http://192.168.0.1`。
- **不要**先刷 ponwrt 再刷 QWRT（多绕一圈）；直接从 U-Boot recovery 装 QWRT。

---

## 2. 刷机流程（从 U-Boot 开始）

> 阶段 0–3（准备、拿 root、备份、factory 转换）见 `01` / `03`；这里从「已经能进 U-Boot recovery」开始。

### 2.1 进 U-Boot recovery

- 网线插 **LAN2/3/4**（**不要插 2.5G 的 LAN1**；U-Boot 没有 2.5G PHY 驱动）。
- `http://192.168.0.1/`，首启等 60–90 秒；PC 可静态 `192.168.0.10/24`。

### 2.2 首次安装五步（QWRT 版）

1. **Rebuild UBI / 重建 UBI** —— 创建 `fip / ubootenv / ubootenv2 / factory / fit` 卷。
2. **Write fip / 写入 fip** —— 上传 `物料/引导/an7581-fiberhome-hg5585f-ct-bl31-u-boot.fip`。
3. **Restore board data / 恢复板级数据** —— 上传 `factory-1m.bin`（**必须**，QWRT 的 PON 和闭源 WiFi 都靠它）。
4. **Upload system / 上传系统** —— 上传 **QWRT** 的 `QWRT-R26.10.18-…-ct-squashfs-sysupgrade.itb`（约 40 MB；**不要**在这里传 ponwrt 包）。
5. **Boot system / 启动系统**。

> QWRT 的 `lib/upgrade/platform.sh` 对 CT 走 `fit_check_image` + `airoha_require_ubi_layout factory && fit_do_upgrade`；U-Boot 的「Install system」直接写 `fit` 卷，不需要先有 OpenWrt。`rootfs_data` 会被重建，**不保留配置**。

### 2.3 预期现象

- 约 1–3 分钟后 QWRT 启动；PC 在 **LAN2/3/4** 上 DHCP 拿到 `192.168.1.x`，网关 `192.168.1.1`。
- 默认账号：**root / `password`**（`97-default-settings` 写入的 MD5 crypt；本机已改为 `Qazswxdecf1`）。
- **Telnet 23 默认开启**（`S50telnetd`），SSH 22 开启（dropbear）。
- `lan1`（2.5G）默认是 **WAN**，会尝试 DHCP；没有接上游时它没地址，不影响 LAN 访问。

> ⚠️ 如果 2.5G 口没反应：QWRT 也**没有 PR #34 修复**，但 QWRT DTB 用的是旧 C45 写法 + 800ms 复位，暖重启可能偶发 `lan1` NO-CARRIER。第一次先冷启动，别用 2.5G 当唯一管理口。

---

## 3. 首启：先离线改 LAN、改密码

**不要**在默认 `192.168.1.1` 下把 QWRT 接到家里网络（会和光猫/现网撞段）。PC 直连 LAN2/3/4，先做：

> 本机 2026-10-21 实刷时只接了 PC、未接家里网络，所以**保留了 `192.168.1.1`**（PC 在 lan4，改网络不会断）。如果你准备把它接入现网，先按下面改成 `192.168.88.1`（或最终要替换 ponwrt 时改 `192.168.31.1`）。

```sh
# 浏览器 http://192.168.1.1 ，root / password（本机已改 Qazswxdecf1）
# 或 telnet 192.168.1.1 / ssh root@192.168.1.1

uci set network.lan.ipaddr='192.168.88.1'
uci set network.lan.netmask='255.255.255.0'
uci commit network
/etc/init.d/network restart
```

PC 重新拿 `192.168.88.x`，后台变 `http://192.168.88.1`。

```sh
passwd                                  # 改 root 密码（默认 password 太弱）
uci set system.@system[0].hostname='ct-qwrt'
uci set system.@system[0].timezone='CST-8'
uci set system.@system[0].zonename='Asia/Shanghai'
uci commit system

# Telnet 默认开：如果只打算用 SSH，建议关掉
/etc/init.d/telnetd disable
/etc/init.d/telnetd stop
```

> QWRT 的 `/etc/config/wireless` 首启由 `mtwifi` 生成，**默认 `encryption=none`（开放 SSID）**。改完 LAN 后第一件事就是去「网络 → 无线」设 WPA2 密码，别让开放 AP 挂着。

---

## 4. PON 配置（QWRT 的 LuCI 与 ponwrt 同源）

QWRT 默认 `pon.line0.mode` 为空、`operator=ctc`、`ge_ports=1`。进 `网络 → PON`（QWRT 的 `luci-app-pon`）：

| 项 | 值 | 说明 |
|---|---|---|
| Line mode | **`epon-10g-1g`** | 10G/1G 非对称；不要选 10g-10g |
| OAM profile | **`ctc`**（默认已是） | `ieee` 会 service_ready=0 |
| LOID | 自家线路 LOID | 同 `03` |
| LOID password | 留空 | EPON 只认 LOID |
| **Ethernet port count (`ge_ports`)** | **填 `4`** | CT 面板 4 口（1×2.5G + 3×GE）；现网 ponwrt 实测 4 可用。**2026-10-21 QWRT 实刷采用 4，PON 服务已按 `epon-10g-1g` 启动**；PON 业务本身待接光纤验证。异常时可试 3 |

等价 UCI：

```sh
uci set pon.line0.mode='epon-10g-1g'
uci set pon.line0_oam.operator='ctc'
uci set pon.line0_oam.loid='000000000000000014509791'
uci set pon.line0_oam.ge_ports='4'
uci commit pon
/etc/init.d/pon reload
```

> **本机实刷验证（2026-10-21）**：重启后日志为 `configured=epon-10g-1g`、`PON line mode set to epon-10g-1g`、`serial_number: 46485454c123e98a`（从 board data 读到的正是 CT 的 PON SN），`oam0` 已启动。当前未插光纤，日志 `optical signal absent`。

### 4.1 板级数据

QWRT 的 `factory` 卷同样要 1 MiB（`03_pon_data`：`pon_data_target factory ubi 1048576`，身份字段在 `0x2000/0x2010/0x2020`）。**U-Boot 第 3 步恢复板级数据就是写它**，正常情况下不需要再上传。

验证：

```sh
# 1 MiB factory 卷是否存在、内容对不对
ubinfo -a 2>/dev/null | head -40
# 找 factory 卷的 ubi volume，读 0x2000 起 6 字节 = MAC
# 或直接看 QWRT LuCI → PON → 硬件/board data 页面
```

若 U-Boot 恢复被跳过/失败：QWRT 的 LuCI PON 配置页有 **PON board data** 上传入口（页面源码里 `Writing board data failed`），可补传 `factory-1m.bin`。

### 4.2 接光纤后的判据

```sh
cat /sys/kernel/debug/airoha-xpon-pon0/line
#   lifecycle: operational
cat /sys/kernel/debug/airoha-xpon-pon0/registration
#   LLID 有效 / service_ready: 1
/usr/sbin/ponctl --help 2>/dev/null | head    # 若想看 ponctl 原生命令
```

> QWRT 的 PON 用户态是 `airoha-pond` + `ponctl`，与 ponwrt 同一套 Airoha 栈；`epon-10g-1g` + `ctc` 的经验可直接搬。

---

## 5. 网络形态：QWRT 默认是「lan1=WAN」，你要选一种

QWRT 的 `02_network` 对 CT 写死：

```
lan2 lan3 lan4  →  LAN（br-lan）
lan1            →  WAN（DHCP 客户端）
```

### 形态 A：旁挂 AP / 实验机（最简单）

- WAN（lan1）不接，LAN（lan2-4）接家里交换机/PC。
- LAN 已改 `192.168.88.1`；**关 DHCP** 或保持独立网段，避免和现网 `192.168.31.0/24` 冲突。
- 2.5G 口当 WAN 闲着；想用 2.5G 当 LAN，见形态 B 的「把 lan1 并进 br-lan」。

### 形态 B：PPPoE 主路由（替代现网 ponwrt）

需要三步：建 `pon0.995`、把 WAN 改到它、把 lan1 并进 LAN。

```sh
# 1) WAN 直接指到 pon0.995（QWRT 会自动创建 VLAN 子接口；若没出现，
#    再显式建 network.pon0_995 8021q 设备，见下方备选）
uci set network.wan.device='pon0.995'
uci set network.wan.proto='pppoe'
uci set network.wan.username='02105250448'
uci set network.wan.password='052356'
uci set network.wan.ipv6='1'
uci set network.wan.mtu='1492'
uci set network.wan.mru='1492'
uci set network.wan.keepalive='5 5'
uci set network.wan6.device='pon0.995'
uci commit network

# 2) 把 lan1（2.5G）并进 br-lan
uci add_list network.@device[0].ports='lan1'
uci commit network
/etc/init.d/network reload
```

之后 `ip -br link` 应看到 **`pon0.995@pon0`**；`ifstatus wan` 在接光纤后应有 IPv4；`br-lan` 含 lan1–lan4。

> **本机 2026-10-21 实刷已按形态 B 配好**：`pon0.995` 已创建、WAN=PPPoE、`br-lan` 含 lan1–lan4，LAN 保留 `192.168.1.1`。重启后配置持久化；因未接光纤，`pon0`/`pon0.995` 仍是 LOWERLAYERDOWN。
>
> 备选（仅当 `pon0.995` 没自动出现）：
>
> ```sh
> uci set network.pon0_995='device'
> uci set network.pon0_995.name='pon0.995'
> uci set network.pon0_995.type='8021q'
> uci set network.pon0_995.ifname='pon0'
> uci set network.pon0_995.vid='995'
> uci commit network
> ```

> 如果你不打算用 PPPoE（例如只当 AP/交换机），**不要**做形态 B，保持 lan1=WAN 不动。
> VLAN 995 是联通家宽参数；CT 原厂电信配置不适用。

---

## 6. WiFi（闭源 `mt7916_ap.ko` + `mtwifi`）

QWRT 的 WiFi 与 ponwrt 完全不同：

- 驱动：闭源 `mt7916_ap.ko` + `mtwifi` 用户态；接口名 **`ra0` / `rai0`**（不是 `phy0-ap0`）。
- 首启：`/etc/init.d/mtwifi` 在 `/etc/config/wireless` 不存在时执行 `/sbin/wifi config`，生成默认配置；**默认 `encryption=none`**，SSID 是 `QWRT-2.4G` / `QWRT-5G`。**本机已改为 `ct-qwrt` / `ct-qwrt_5G` + WPA2 PSK (CCMP)。**
- 校准：从 `factory` 卷 `0x1000` 读 4 KiB EEPROM，要求首两字节 `16 79`。**没恢复 factory 就没有 WiFi**。

首启后：

```sh
# 看接口/驱动
iw dev 2>/dev/null
iwinfo
dmesg | grep -Ei 'mt7916|mtwifi|eeprom|ra0|rai0' | tail -30

# 改 SSID/密码（LuCI 网络→无线更直观；UCI 示例，注意本包 QWRT 的节名是 ra0/rai0）
uci set wireless.ra0.ssid='ct-qwrt'
uci set wireless.ra0.encryption='psk2'
uci set wireless.ra0.key='你的密码'
uci set wireless.rai0.ssid='ct-qwrt_5G'
uci set wireless.rai0.encryption='psk2'
uci set wireless.rai0.key='你的密码'
uci commit wireless
wifi reload
```

- 2.4G 建议 ch6/HT20 或 HE20；5G 建议 ch149/80（与现网 ONT/小米 AP 错开，见 `AGENTS.md` 的 WiFi 记录）。
- QWRT 闭源驱动对 160MHz/HE 的支持取决于 SKU 文件与法规；测试期先用 80MHz。
- 若 `ra0/rai0` 没出现：先查 `factory 0x1000` 的 `16 79`，再查 `dmesg` 的 EEPROM/固件加载错误；不要急着重刷。

---

## 7. 2.5G 口与暖重启（QWRT 的已知短板）

- `lan1` 是 GPY211C 2.5G，QWRT DTB 用 **旧 C45 写法** `ethernet-phy-ieee802.3-c45`、`reset-deassert-us=800000`，**没有 PR #34 的显式 PHY ID 修复**。
- 结果：**暖重启后 `lan1` 可能 NO-CARRIER**（和 PR #34 描述的竞态同类），冷启动恢复；QWRT 的 800ms 复位可能降低概率，但未实测。
- 测试：

```sh
cat /sys/class/net/lan1/carrier
cat /sys/class/net/lan1/speed        # 2500（对端支持时）
ethtool lan1 2>/dev/null | grep -E 'Speed|Link detected'
reboot    # 连续 3 次，每次起来看 lan1
```

- 若暖重启后 `lan1` 不亮：冷启动；把管理口换到 lan2-4；记录到 `数据模板/刷机记录.md`。
- 如果 2.5G 对稳定性要求高，**ponwrt 的 PR #34 修复更靠谱**——这是选 QWRT 的主要代价之一。

---

## 8. 软件源 / 代理（QWRT 的最大坑）

### 8.1 feeds 不匹配

QWRT 镜像自带 `/etc/opkg/distfeeds.conf` 指向 **OpenWrt 25.12.3**；但首启 `uci-defaults/13_opkg_update` 会把它**覆盖成 ImmortalWrt 24.10.6（北大镜像）**：

```sh
cat /etc/opkg/distfeeds.conf
# 首启后大概率是：
# src/gz openwrt_base http://mirrors.pku.edu.cn/immortalwrt/releases/24.10.6/...
```

这跟 25.12.3 / 5.4.302 内核**不匹配**，`opkg update` 可能拉到 ABI 不兼容的包。建议：

- **不要**在没核对 feeds 前 `opkg update && opkg install`；
- 先用镜像自带的组件（openclash / xray / SSR-Plus）；
- 真要装包：把 feeds 改回与镜像匹配的源（或 QWRT 自己的源），并接受“包可能没有/ABI 不符”的风险；
- 记录改动，别把系统搞成半升级状态。

### 8.2 代理：没有 Passwall

- 自带：`openclash`（`/etc/init.d/openclash`，配置 `/etc/config/openclash`）、`xray` 二进制（`/usr/bin/xray`，无 LuCI 前端）、`luci-app-ssr-plus` 初始化脚本/配置目录。
- **没有** Passwall / sing-box。
- 你现网是 Passwall + xray + chinadns-ng 的一套规则；QWRT 上**不能直接导入**，要么：
  1. 用 openclash（Clash 订阅/规则）重建；
  2. 手工跑 xray + 自建 nft/tproxy 规则（工作量大）；
  3. 只用 QWRT 做 AP/主路由，代理交给旁边设备。
- 如果代理是刚需，**先留 ponwrt**（自带 Passwall），QWRT 只作 WiFi/2.5G 验证。

---

## 9. 验收清单（QWRT）

| # | 检查 | 命令/位置 | 期望 |
|---|---|---|---|
| 1 | 系统版本 | `cat /etc/openwrt_release` | QWRT R26.10.18 / 25.12.3 |
| 2 | 内核 | `uname -r` | 5.4.302 |
| 3 | LAN | `ip -4 addr show br-lan` | 192.168.88.1 |
| 4 | 默认账号 | telnet/ssh root | `password` 已改 |
| 5 | Telnet | `ss -lntp | grep :23` | 已按需关闭 |
| 6 | PON 模式 | `uci get pon.line0.mode` | `epon-10g-1g` |
| 7 | OAM | `uci get pon.line0_oam.operator` | `ctc` |
| 8 | ge_ports | `uci get pon.line0_oam.ge_ports` | 4（或 3） |
| 9 | factory | `ubinfo -a` / board data | 1 MiB 卷存在，0x2000 MAC 正确 |
| 10 | PON 线路 | debugfs line | `operational`（接纤后） |
| 11 | PON 注册 | debugfs registration | `service_ready: 1` |
| 12 | PPPoE | `ifstatus wan` | 有 IPv4（若配置） |
| 13 | 2.5G | `cat /sys/class/net/lan1/carrier` | 1；暖重启 ×3 观察 |
| 14 | WiFi | `iw dev` / `iwinfo` | `ra0`/`rai0` 存在 |
| 15 | WiFi 加密 | LuCI 无线 | WPA2，非 none |
| 16 | 温度/内存 | thermal / `free -m` | <85°C / 可用 >150 MB |
| 17 | 配置备份 | `sysupgrade -b /tmp/qwrt-config.tar.gz` | 生成并拉回 PC |

---

## 10. 切换 / 回滚

| 目标 | 做法 |
|---|---|
| QWRT → ponwrt CT | U-Boot recovery → **Install system** → 传 `ponwrt-…-ct-squashfs-sysupgrade.itb`（最稳）；或在 QWRT 里 `sysupgrade -F` 传 ponwrt 包（两者 `supported_devices` 都是 CT，但建议走 U-Boot） |
| ponwrt → QWRT | 同上，传 QWRT 包 |
| QWRT 升级 QWRT | `sysupgrade` 传新 QWRT CT 包（`REQUIRE_IMAGE_METADATA=1`，白名单 CT） |
| 回原厂 | **仍然不可能**（CT 原厂固件没有公开包）；只能靠刷前全分区备份，且恢复流程未验证（见 `05`） |
| 救砖 | 串口 3 秒窗口 → bootmenu → Web recovery（见 `05`） |

> QWRT 的 `platform_do_upgrade` 要求 `factory` UBI 卷存在；如果 UBI 被破坏，先在 U-Boot 里 Rebuild UBI + 恢复板级数据，再装系统。

---

## 11. 风险与注意（QWRT 专属）

1. **老内核 5.4.302**：不能套用 ponwrt/6.18 的驱动/调优经验；出问题先怀疑内核差异。
2. **无 PR #34**：暖重启 `lan1` 可能不亮；冷启动/换管理口是临时对策。
3. **reset 键 DTB=GPIO0**：与实际 GPIO35 不符；内核侧按键可能无效（U-Boot 侧另说）。不要依赖 reset 键进 failsafe。
4. **默认开放 WiFi**：首启必须先设 WPA2，别让 `encryption=none` 挂着。
5. **feeds 被改成 24.10.6**：`opkg update` 前先核对，别把系统搞成 ABI 混装。
6. **没有 Passwall**：现网分流不能直接搬；代理刚需就留 ponwrt。
7. **默认 lan1=WAN**：管理口插 lan2-4；要 2.5G 当 LAN 必须手工并进 `br-lan`。
8. **默认 LAN 192.168.1.1**：与光猫/现网可能撞段；首启离线改 `192.168.88.1`。
9. **仍要 factory 1 MiB**：PON + 闭源 WiFi 都依赖；没恢复就是“有系统没 WiFi/没 PON”。
10. **共享的 telnet 工具已静态评估**：本身无恶意，但无签名、会起 `powershell` 子进程、会写 `cfg_cmd` 持久化；优先用 `脚本/fhtool-ct.py`，非要用 EXE 就先 `--probe`、单线直连、抓包、跑前备份。

---

## 12. 结论

- **QWRT 值得一试**：闭源 WiFi + 原生 CT DTB + 2.5G 口，是这台机器刷第三方固件的主要理由。
- **但它不是“更好的 ponwrt”**：老内核、无 PR#34、无 Passwall、feeds 坑、默认开放 WiFi/默认 lan1=WAN，都需要接受和手工处理。
- **建议路径**：先按本文刷 QWRT → 验证 WiFi/2.5G/PON → 再决定是否长期留 QWRT；如果代理是刚需，回 ponwrt（`01`）或把代理放到旁路设备。
- 无论刷哪个，**刷前备份 + factory 1 MiB** 是唯一不可重来的东西。
