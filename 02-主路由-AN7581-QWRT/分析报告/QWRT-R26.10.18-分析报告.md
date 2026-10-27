# QWRT-R26.10.18-airoha-an7581-fiberhome_hg5585f-**ct**-squashfs-sysupgrade.itb 逆向分析报告

> 分析日期 **2026-10-20** ｜ 分析对象 sha256 `5053531F…7450AE53` ｜ 目标机 烽火 HG5585F **CU**（联通版，当前跑 ponwrt）
> 结论一句话：**包是真的、签名是真的、硬件是同一块板，但它是 CT 变体，直接刷会让你 LAN1 网口失效 + 默认网络不对。**

---

## 0. 结论速览

| 问题 | 答案 |
|---|---|
| 包本身完整吗？ | ✅ FIT 三个子镜像 crc32 + sha1 全部校验通过，ucert 签名链完整 |
| 能通过 sysupgrade 校验吗？ | ❌ 被设备白名单挡住：`Device fiberhome,hg5585f-cu not supported by this image`（可 `-F` 强刷） |
| 硬件对得上吗？ | ⚠️ 同一块板（AN7581 + MT7916 + 同一 UBI 布局 + 同一 factory 偏移），**只有网口 PHY 接法不同** |
| 刷了会怎样？ | **LAN1 变砖（无 PHY）**，默认 WAN 指向 lan1 所以上不了网；其余口/无线/PON 都能起来 |
| 建议 | **先别刷**（用户 2026-10-20 已拍板），等 CU 适配版或改包 |

---

## 1. 包结构（FIT）

```
magic        d00dfeed          totalsize 4096（FIT 头只有 4 KiB）
timestamp    1792306502        2026-10-18 06:55:02 UTC
description  ARM64 QWRT FIT (Flattened Image Tree)

images/
  kernel-1   pos 0x001000  size  4,579,254  gzip  Linux-5.4.302  load/entry 0x8a000000
  fdt-1      pos 0x45f000  size     14,698  none  fiberhome_hg5585f-ct DTB
  rootfs-1   pos 0x463000  size 37,552,128  none  SquashFS 4.0 / XZ / 1MiB cluster
configurations/
  config-1   kernel=kernel-1  fdt=fdt-1  loadables=rootfs-1
```

尾部 839 字节：`sysupgrade-metadata` JSON + ucert 签名（`Local build key`，key id `215087f5c3341288`）。

```json
{ "metadata_version":"1.1", "compat_version":"1.0",
  "supported_devices":["fiberhome,hg5585f-ct","fiberhome,hg5585f-ct-usb-sfp"],
  "version": { "dist":"OpenWrt","version":"25.12.3","revision":"r7856-44e450dae4",
               "target":"airoha/an7581","board":"fiberhome_hg5585f-ct" } }
```

**校验结果（全部 OK）**

```
kernel-1  crc32 e2f48197  sha1 7cc94d68…5b22
fdt-1     crc32 a0ab8981  sha1 576ece70…2243
rootfs-1  crc32 f6c4e405  sha1 58186354…bf3
fit_check_sign -f …  →  exit 0
```

> 注：`fit_check_sign` 只验 hash，**不验 ucert 签名**。签名校验走 `validate_firmware_image` → `fwtool` + `ucert`，这一层也过了（`fwtool_signature: true`）。

---

## 2. 硬件适配差异（关键）

DTB `compatible = fiberhome,hg5585f-ct / airoha,an7581 / airoha,en7581`，与 ponwrt 源码里的 `an7581-fiberhome-hg5585f-ct-common.dtsi` 完全对应：

| 项 | QWRT 这个 CT 包 | 你的 CU 机器（ponwrt 实测） |
|---|---|---|
| `chosen/rootdisk` | phandle 2 → UBI `fit` 卷 | UBI `fit` 卷（同） |
| 网口 PHY | **lan1 = MDIO `ethernet-phy@7`（GPY211C 2.5G 外置）**，lan2-4 = 内建 PHY2/3/4 | **lan1-4 = 全部内建 PHY1/2/3/4** |
| 2.5G 口 | `gdm4` + `phy-mode=2500base-x` + `reset-gpios GPIO34` | **没有 gdm4 这个口** |
| WAN 口 | `02_network`：`lan1` 作 WAN，lan2-4 作 LAN | `pon0` 作 WAN（PON 直拨 PPPoE） |
| 内部 PHY1 | **未启用**（CT 用外置 GPY211 占 lan1） | **在用**（`mt7530-0:09` 驱动 `Airoha AN7581 PHY`，dmesg 实证） |
| LED | `blue:usb-1` 只有 1 个 USB LED | 双 USB LED（`usb1`/`usb2`） |
| reset 键 | DTB `keys/reset` = **GPIO0** | 实际 **GPIO35**（U-Boot 与 ponwrt 都用 35） |

**后果**：刷进去后 `lan1` 拿不到 PHY → 链路起不来。你现在这台机器所有设备都挂在 LAN1（`bridge fdb` 实证 PC/平板/AP 全在 `dev lan1`），**刷完必须换到 LAN2/3/4 才能进后台**。而 QWRT 默认 `wan=lan1`，等于默认没网，得手改 `pon0.995` PPPoE。

**能对上的部分**（说明这是同一块板，改包可行）：UBI 卷序 `fip/ubootenv/ubootenv2/factory/fit/rootfs_data`、`factory` 偏移（`0x2000` MAC / `0x2010` PON SN / `0x2020` SN）、`pon_data` 1 MiB、`03_pon_data` 里 `hg5585f-cu` 与 `-ct` 写在同一个 case 分支。

---

## 3. 固件内部（rootfs 拆解）

### 3.1 系统

- **OpenWrt 25.12.3 r7856-44e450dae4**（不是 24.10，也不是 ImmortalWrt）
- **内核 Linux 5.4.302**（`lean@lean-esx`, gcc 14.3.0）— 走 **Airoha BSP 5.4**，不是 6.18 mainline
- 包管理 **opkg**（`/bin/opkg` + `/etc/opkg/distfeeds.conf` 指 `downloads.openwrt.org/releases/25.12.3/…`）
- 界面 QWRT 自己的（banner `http://www.q-wrt.com`，"The core of SmartRouters"），有 `luci-app-*` 一堆 + iStore 风格脚本

### 3.2 PON 栈（跟 ponwrt 同源）

- 驱动：`airoha-xpon.ko`、`airoha-paged-bosa.ko`、`airoha-pon-frontend-core.ko`
- 用户态：`/usr/sbin/airoha-pond`（Rust，含 `src/oam/ctc.rs` 与 `src/oam/ieee.rs`）、`/usr/sbin/ponctl`
- **`ponctl` 支持的模式字符串**：`gpon xgpon xgspon epon-1g epon-10g-1g epon-10g-10g` → **`epon-10g-1g` 在列** ✅
- `/etc/config/pon` 默认 `option operator 'ctc'`、`option ge_ports '1'` → **ctc 已默认**，但 **ge_ports 得从 1 改成 4**
- 状态页 `/www/luci-static/resources/view/pon/{status,config,hardware,diagnostics}.js` 齐全

> 这条很关键：**PON 部分 QWRT 和 ponwrt 是同一套 Airoha 栈**，所以你 10-19 踩过的 `operator=ctc` + `epon-10g-1g` + LOID 那套配置经验可以直接搬。

### 3.3 无线

- **闭源驱动 `mt7916_ap.ko`（14.4 MB）+ `mtwifi` 用户态**，不是 mainline mt76/mt7915e
- `/etc/Wireless/l1profile.dat` 声明 `INDEX0=MT7916`，`INDEX0_main_ifname=ra0;rai0` → **接口名是 `ra0`/`rai0`，不是 `phy0-ap0`**
- **WiFi 校准直接从 `factory` 卷 0x1000 读 4 KiB**（`etc/hotplug.d/firmware/10-mt7916-an-eeprom`，要求首 2 字节 `16 79`）
  - 实测你机器 `dd if=/dev/ubi0_3 bs=4096 skip=1 count=1` → **`16 79 00 00 00 0c 43 26 60 00 …`** ✅ **magic 对得上**
- 好处：闭源驱动理论上比 ponwrt 的 `mt7915e` 更稳（ponwrt 那边 `Failed to setup PHY LED pinctrl` 刷屏、NPU 卸载没生效）
- 代价：`ra0/rai0` 命名跟 OpenWrt 标准 `wifi` 体系不一样，脚本/规则要重写；而且 **`/etc/config/wireless` 在 rootfs 里不存在**，首次开机由 `mtwifi` 生成

### 3.4 默认身份 / 首启行为

| 项 | 值 | 来源 |
|---|---|---|
| root 密码 | **`password`** | `97-default-settings` 把 `root::…` 替换成 `$1$V4UetPzk$CYXluq4wUazHjmCDBCqXF.`，**openssl 反查 = `password`**（实测命中） |
| 额外账号 | `telnet` 同名同 hash | `/etc/shadow` |
| hostname | `iStoreOS`（仅当 `/usr/sbin/quickstart` 存在；本包没有 → 走默认 `OpenWrt`） | `97-default-settings` |
| 默认 LAN IP | **`192.168.1.1`** | `bin/config_generate:165` `lan) ipad=${ipaddr:-"192.168.1.1"}` |
| SSH | dropbear 22，`PasswordAuth on` / `RootPasswordAuth on` | `/etc/config/dropbear` |
| opkg 源 | 被 sed 成 `mirrors.cloud.tencent.com/lede` | `97-default-settings` |

> ⚠️ **默认 LAN 是 `192.168.1.1`，跟光猫原厂地址撞**。你家里是 `192.168.31.0/24`，刷完要么改 QWRT 的 LAN 段，要么临时直连改。

### 3.5 内置代理 / 应用（跟你的 dae 体系不兼容）

- **没有 passwall / daed / sing-box**
- 有 **openclash**（`/etc/config/openclash` 7.8 KB + `GeoSite.dat` 10 MB）、**shadowsocksr**（`ssr-local`/`ssr-redir`/`ssr-rules`）、**xray 二进制 30 MB**（`/usr/bin/xray`，无 LuCI 前端）
- 还有：3proxy、microsocks、openvpn、samba、vsftpd、xupnpd、vlmcsd、arpbind、autoreboot、ddns、upnpd、diskman、filetransfer
- **`REQUIRE_IMAGE_METADATA=1`**（同 ponwrt），`platform.sh` 里 `hg5585f-cu` 和 `hg5585f-ct` 写在同一个 case 分支 → **`-F` 强刷在升级逻辑层面是允许的**，只是白名单不让

### 3.6 升级脚本（跟 ponwrt 几乎逐字相同）

`/lib/upgrade/platform.sh` 与 ponwrt 的差异只有：QWRT 多了 `airoha_require_ubi_volumes()` 拆函数、`mktemp` 加进 `RAMFS_COPY_BIN`。核心动作一致：

```
airoha_require_ubi_layout factory && fit_do_upgrade "$1"
```

→ `export_fitblk_bootdev`（读 `chosen/rootdisk` → `CI_KERNPART=fit`, `CI_UBIPART=ubi`, `CI_METHOD=ubi`）→ `fitblk /dev/fit0` 释放 → `nand_do_upgrade` → `nand_upgrade_fit`：

```sh
nand_upgrade_prepare_ubi "" "" "$fit_length" "1"   # ubirmvol fit + rootfs_data，再 ubimkvol
cat "$fit_file" | ubiupdatevol /dev/ubi0_4 -s "$fit_length" -
```

**`rootfs_data` 会被删掉重建**（`nand.sh:218`）→ **刷机不保留配置**。要保留得先 `sysupgrade -b` 备份再 `-f` 恢复。

---

## 4. U-Boot 侧（从你机器的 fip 卷解出来，跟你实际跑的完全一致）

`strings /dev/ubi0_0` 解 LZMA 得到 `U-Boot 2026.07-gd5b173d17470 (Sep 23 2026)`，默认环境：

```
bootcmd=run boot_ubi
boot_ubi=run boot_production ; echo System boot failed, starting Web recovery ; run boot_recovery
boot_production=led $bootled_status on ; run ubi_read_production && bootm $loadaddr
ubi_read_production=run ubi_mount && ubi read $loadaddr fit && iminfo $loadaddr && run ubi_prepare_rootfs
ubi_write_production=… ubi create fit $filesize dynamic && ubi write $loadaddr fit $filesize && run ubi_verify_production
boot_recovery=httpd dhcp
bootmenu_title=U-Boot HG5585F CU
bootmenu_0=Boot system / bootmenu_1=Web recovery / …
```

**关键结论：`bootm` 不带 `#config-1`**，所以 U-Boot 走 FIT 默认配置（`configurations/default = config@1`）。QWRT 包默认配置名就是 `config@1` → **能正常引导，不用改 U-Boot 环境**。✅

**另一个关键点（风险）**：`boot_ubi` 只有在 `ubi read` / `iminfo` **失败**时才 fallback 到 Web recovery。如果内核起来了但 **panic / 卡在 init**，U-Boot 已经交棒，**不会自动回退**。回滚唯一通道是**开机 3 秒内打断 autoboot**（`bootdelay=3`，串口日志实证 `Hit any key to stop autoboot: 3 → 2 → 1`）。

⚠️ **reset 键在这版 U-Boot 里没有绑任何恢复动作**（`check_buttons` 在这个 env 里不存在；QWRT 的 DTB 还把 reset 指到 GPIO0）。所以**不能靠"按住 reset 开机"进 recovery**，只能串口打断或走菜单。

---

## 5. 如果哪天真要刷（预案，未执行）

### 5.1 直接强刷 CT 包（最小动作，风险中等）

```sh
# 1) 备份当前配置（已做：/tmp/ponwrt-backup-20261020-1226.tar.gz → 已拉到 PC）
sysupgrade -b /tmp/ponwrt-backup.tar.gz

# 2) 上传后强刷（会清 rootfs_data）
sysupgrade -F -n /tmp/QWRT-…-ct-…itb

# 3) 起来后（LAN1 无效 → 网线插 LAN2/3/4，PC 设 192.168.1.x）
#    ssh root@192.168.1.1  密码 password
uci set network.lan.ipaddr='192.168.31.1'   # 避开光猫 192.168.1.1
uci set pon.line0.mode='epon-10g-1g'
uci set pon.line0_oam.operator='ctc'
uci set pon.line0_oam.loid='000000000000000014509791'
uci set pon.line0_oam.ge_ports='4'
# 新建 pon0.995 + PPPoE（02105250448 / 052356）→ commit → reboot
```

刷完**不可用**的部分：`lan1`（无 PHY）、双 USB LED（只配了 1 个）、reset 键（GPIO0）。

### 5.2 改包成 CU 适配版（更贴合，但属自制品）

要改 4 处：

1. **DTB**：`compatible` → `fiberhome,hg5585f-cu`；`port@1` 的 `phy-handle` 从 `phy@7` 换成内建 `phy@9`（并把 `phy@7`/`gdm4` 相关节点去掉）；`keys/reset` gpios 改 `35`
2. **重算 FIT**：`data-size` 不变（DTB 长度会变，需同步改 `totalsize`/`data-position` 偏移链）、`hash-1` crc32、`hash-2` sha1
3. **尾部 metadata**：`supported_devices` → `["fiberhome,hg5585f-cu"]`、`board` → `fiberhome_hg5585f-cu`
4. **ucert 签名**：改完 metadata 后原签名失效 → 要么重签（需私钥，拿不到），要么删签名段走 `-F` 强刷

> 第 4 步是死结：**没有大雕的签名私钥，改完的包一定过不了 `fwtool_signature`**，只能 `-F`。既然都要 `-F`，改包只是把"网口不对"换成"网口对但包是自制的"，收益是 LAN1 能用，代价是引入新变量（DTB 改错直接不启动）。**这也是建议先别刷的理由之一。**

### 5.3 回滚

```sh
# 从当前 ponwrt 回滚（本地已有官方 CU 包，sha256 已核对 4b7c3431…f76c）
sysupgrade /tmp/ponwrt-…-cu-squashfs-sysupgrade.itb
```
- **从 QWRT 回 ponwrt**：QWRT 的 `platform.sh` 同样认 `hg5585f-cu` 分支，`sysupgrade -F` 可行（前提：LAN 通）
- **彻底救砖**：串口 3 秒内打断 → `bootmenu` → `1. Web recovery`（`http://192.168.0.1/`）→ 传 CU 包
- ⚠️ **网线插 LAN2/3/4** 才能进 Web recovery（LAN1 在 CT 包里是死的；不过 U-Boot 阶段的 PHY 是 BSP 自己初始化的，**理论上 U-Boot 下 LAN1 可能是通的**，未验证）

---

## 6. 已为你准备好的东西

| 文件 | 说明 |
|---|---|
| `光猫-HG5585F/backup-ponwrt-20261020/ponwrt-config-20261020-1226.tar.gz` | **当前 ponwrt 配置全量备份**（20.7 KB，`sysupgrade -b` 产物，已从路由器拉到 PC） |
| `QWRT-分析/QWRT-R26.10.18-分析报告.md` | 本文件 |
| `QWRT-分析/kernel-1.gz` / `kernel-1.raw` | QWRT 内核（4.37 MB gz / 9.43 MB 解压） |
| `QWRT-分析/qwt_fdt-1.dtb` | QWRT 设备树（可 `dtc -I dtb -O dts` 反编译） |
| `QWRT-分析/rootfs-1.squashfs` | QWRT 根文件系统（35.8 MB） |
| `QWRT-分析/rootfs/` | 已解开（145 MB，可直接 grep） |
| `QWRT-分析/uboot-cu.bin` | 你机器 U-Boot 解压镜像（含完整默认环境，可查任何 env 变量） |

路由器上的 `/tmp/qwrt-ct.itb` 已删除，**当前 ponwrt 未做任何改动**（`PonWrt SNAPSHOT r0-e585ae8` 仍在线，`/tmp` 已回到 4.3 MB）。

---

## 7. 建议下一步

1. **找 CU 版**：问大雕 / 看发布页有没有 `hg5585f-cu` 包。QWRT 的 `03_pon_data`、`platform.sh`、`02_network` 里**都有 `fiberhome,hg5585f-cu` 分支**，说明源码支持 CU，只是这次没编译出来 —— **大概率要一个 `profile=fiberhome_hg5585f-cu` 的构建**，不是要改代码。
2. 若确实只有 CT 包：等你**愿意拆机接串口**的时候再刷（这样 3 秒窗口有保障），或者接受"改包 + `-F`"。
3. 无论走哪条：**先确认 `mtd13 factory` 3 MiB 原厂备份还在**（`D:\BaiduNetdiskDownload` 之外，你 `C:\Users\29049\Downloads\mtd13-factory.bin` 3,145,728 字节那份），那是 PON 校准 + WiFi EEPROM 的唯一来源。
