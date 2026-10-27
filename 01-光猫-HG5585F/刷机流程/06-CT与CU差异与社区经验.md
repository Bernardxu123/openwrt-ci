# 06 · CT 与 CU 差异、固件取证与社区经验

> 面向：**HG5585F 电信版（CT，带 2.5G 口）** 刷 ponwrt v2026.10.18 的准备工作
> 参照机：工作区 `光猫-HG5585F/` 的**联通版（CU）**，2026-10-19 已实机刷通 ponwrt
> 取证日期：**2026-10-21** ｜ 取证原始输出：`分析/`（索引见 `分析/README-取证说明.md`）
> 本文不替代 `01-刷机流程.md`；本文只回答"两版差在哪、包里到底有什么、哪些说法能信"。

## 证据分级（全文通用）

| 标记 | 含义 |
|---|---|
| **【包内证据】** | 从 CT/CU/QWRT 固件包的字节里直接读出，可用 `分析/` 下脚本复现 |
| **【本机记录】** | 工作区既有材料里的本机实测/运行记录（CU 机、U-Boot 镜像、串口日志），非本次重跑 |
| **【社区/外部资料】** | 恩山帖、GitHub 仓库/PR 等外部信息，**未在本机复现**，附 URL |
| **【推断】** | 我的推理，没有直接证据；不可当结论使用 |

> 铁律：**"包里有 X"不等于"真机上 X 生效"**。本文所有"会不会失效/能不能用"的
> 判断，凡未上机验证的，一律标【推断】或【社区/外部资料】。

---

## 1. 一句话结论

**CT 必须刷 `-ct` 包，CU 包会让 CT 的 lan1（2.5G）失效；反过来 CU 刷 CT 包同样废掉 lan1。**
两版是同一块板（AN7581 + MT7916 + 同一 UBI 布局 + 同一 factory 内部布局），
差别集中在**设备树里 lan1 的接法**，外加 rootfs 里约 4 KiB 的板级文件差异，而不是两套硬件。

| 你的机器 | 只能刷 | 不要刷 |
|---|---|---|
| HG5585F **CT**（电信版） | `ponwrt-…-hg5585f-ct-squashfs-sysupgrade.itb`（+ `-ct` 的 initramfs / firstblock / preloader / fip） | 任何 `-cu` 文件 |
| HG5585F **CU**（联通版） | `ponwrt-…-hg5585f-cu-…` | 任何 `-ct` 文件 |

【包内证据】两个包自报同一构建（`revision = r0-5b12fdb`）、CPU 架构相同、
**kernel 子镜像字节完全相同**（crc32 `9cde829b` / sha1 `89049378…`），
rootfs 只差 4,096 字节（CT 54,796,288 B / CU 54,792,192 B），DTB 差 322 字节。
→ 差异是"板级描述 + 板级文件"，不是两套内核。（`分析/package-check.txt` §2–§3）

---

## 2. 硬件差异表（CT vs CU）

| 项 | CT（电信版） | CU（联通版） | 证据 |
|---|---|---|---|
| SoC / 内存 | AN7581（en7581），DTB 声明 `memory@80000000` 512 MiB | 同（DTB 完全相同） | 【包内证据】两个 DTB 的 `/memory@80000000` 都是 `reg=<0 0x80000000 0 0x20000000>` |
| lan1 | **外置 MaxLinear GPY211C 2.5G**，走 HSGMII/2500base-x，挂交换机 MDIO，复位脚 GPIO34（低有效） | **内建 PHY1**（4×1G 之一） | 【包内证据】CT DTB：`/soc/ethernet@1fb50000/ethernet@4` 使能、`phy-mode=2500base-x`、`openwrt,netdev-name="lan1"`；`/soc/switch@1fb58000/mdio/ethernet-phy@7` = `ethernet-phy-id67c9.de10`、pin34；CU DTB：`ethernet@4` = `disabled`，`port@1`(lan1) + `ethernet-phy@9` = `okay` |
| lan2–lan4 | 3×1G，内建 PHY2/3/4 | 同 | 【包内证据】CT `port@2/3/4` + `phy@a/b/c` 均 okay；`port@1`/`phy@9` 为 disabled |
| 2.5G 通道 | 额外使能 2500base-x PCS：`/soc/pcs@1fa09000 status="okay"` | 该 PCS 无 `status`（= 关闭） | 【包内证据】`分析/dtb-diff.txt` |
| reset 键 | DTB `keys/key-reset`：**GPIO35**（0x23）低有效，`linux,code=408`（KEY_RESTART），debounce 60 ms | **同 GPIO35** | 【包内证据】两个 DTB 都是 `pin 35, ACTIVE_LOW`；与【本机记录】CU 机实际用 35 一致 |
| WPS / RFKILL 键 | GPIO4 / GPIO3（低有效） | 同 | 【包内证据】两个 DTB 相同 |
| LED | 12 个 `gpio-leds`：power、wan(pon)、wan(los)、wan-online、wlan、phone、**usb1+usb2**、lan1–lan4 | 同 12 个 | 【包内证据】`分析/dtb-key-compare.json` 中两版 LED 列表逐项相同 |
| WiFi | MT7916（mt7915e/mt7916 固件），PCIe 两路 | 同 | 【包内证据】两 DTB 的 `pcie@1fc00000/1fc20000` + `wifi@0,0` 节点一致；包内 `kmod-mt7916-*` |
| PON | Airoha XPON + paged BOSA（I2C 0x51 光模块） | 同 | 【包内证据】两 DTB 的 `ethernet@2`(pon) + `pcs@1fa08000` + `optical-front-end@51` 相同 |
| factory 卷内部布局 | calibration@0（2 KiB）、**eeprom@1000（4 KiB）**、mac@2000（6 B）、pon-serial@2010（8 B）、device-serial@2020（32 B） | **完全相同** | 【包内证据】两 DTB 的 `ubi-volume-factory/nvmem-layout` 逐项相同 |
| UBI 卷序 | `fip / ubootenv / ubootenv2 / factory / fit`，`chosen/rootdisk` → `fit` | 同 | 【包内证据】两 DTB `ubi-volume-*` 列表与 `rootdisk` phandle(=2) 相同 |
| 引导三件套 | firstblock / preloader / fip **各自独立一套** | 与 CT **逐字节不同** | 【包内证据】`分析/package-check.txt` §7（长度同、sha256 全不同） |

**结论**：CT/CU 是同一块 PCB 的两种贴片/接法。除 lan1 通道外，键、灯、PON、WiFi、
factory、UBI 布局**都一致**——这也是"改包可行"的物理基础，但**不代表可以混刷**。

---

## 3. 固件取证结果（包内证据）

### 3.1 FIT 结构（`ponwrt-…-ct-squashfs-sysupgrade.itb`，60,727,597 B，sha256 `7d04c755…65f9`）

```
magic d00dfeed  totalsize 4096  version 17  struct@0x38 len 0x4b8  strings@0x4f0 len 0x8e

kernel-1  type=kernel      gzip  pos=0x001000  size= 5,900,203  "ARM64 OpenWrt Linux-6.18.55"  load=0x8a000000
fdt-1     type=flat_dt     none  pos=0x5a2000  size=    23,281  "ARM64 OpenWrt fiberhome_hg5585f-ct device tree blob"
rootfs-1  type=filesystem  none  pos=0x5a8000  size=54,796,288  "ARM64 OpenWrt fiberhome_hg5585f-ct rootfs"
config-1  kernel=kernel-1  fdt=fdt-1  loadables=rootfs-1
```

- 三个子镜像的 `hash@1`(crc32) / `hash@2`(sha1) 都**重新算过并对上**（fdt-1 另解出
  sha256 `50f19344…ecb3`）。
- `totalsize` 只有 4096 是因为子镜像按**绝对 data-position** 追加在 FIT 之后，
  不是包损坏。

### 3.2 尾部 sysupgrade-metadata（0x39ea008，276 B JSON）

```json
{"metadata_version":"1.1","compat_version":"1.0",
 "supported_devices":["fiberhome,hg5585f-ct","fiberhome,hg5585f-ct-usb-sfp"],
 "version":{"dist":"PonWrt","version":"SNAPSHOT","revision":"r0-5b12fdb",
            "target":"airoha/an7581","board":"fiberhome_hg5585f-ct"}}
```

- **sysupgrade 白名单 = `fiberhome,hg5585f-ct` / `fiberhome,hg5585f-ct-usb-sfp`**
  （CU 机上是 `fiberhome,hg5585f-cu`，所以 CU 机刷 CT 包会被挡，需 `-F`；反向同理）。
- JSON 之后 16 字节签名段头 `FWx0 …`；**包内没有 usign 签名文本 → ponwrt 的 CT/CU 镜像未签名**
  （QWRT 的 CT 包是带签名 `Local build key` 的，见 §7）。
- 同目录 `profiles.json` 的 `"git_commit":"5b12fdbce807…696f"` 与包内 `r0-5b12fdb` 吻合。

### 3.3 DTB（fdt-1，23,281 B）关键字段

- 根：`model = "FiberHome HG5585F CT"`，`compatible = "fiberhome,hg5585f-ct", "airoha,an7581", "airoha,en7581"`。
- 2.5G 通道：
  - `/soc/ethernet@1fb50000/ethernet@4`：`status=okay`、`phy-mode="2500base-x"`、
    `openwrt,netdev-name="lan1"`、`phy-handle` → `…/mdio/ethernet-phy@7`
  - `/soc/switch@1fb58000/mdio/ethernet-phy@7`：
    **`compatible = "ethernet-phy-id67c9.de10"`**（GPY211C）、`reg=<7>`、
    `reset-gpios=<&pinctrl 34 ACTIVE_LOW>`、`reset-assert-us=100000`、`reset-deassert-us=100000`
  - `/soc/pcs@1fa09000`：`status=okay`（2500base-x PCS）
  - `/soc/switch@1fb58000/ports/port@1` 与 `mdio/ethernet-phy@9`：`status=disabled`
- reset 键：`/keys/key-reset`，`gpios=<&pinctrl 35 ACTIVE_LOW>`，`linux,code=<408>`。
- **lan1 是否 2.5G？是**——但它是"独立 MAC 通道 + 外置 PHY"，不在交换机的 4 个
  internal PHY 里；这就是 CT 与 CU 唯一实质差异。

### 3.4 与同版本 `-cu` 包 DTB 对照

| DTB 项 | CT 包 | CU 包 |
|---|---|---|
| `model` / `compatible` | FiberHome HG5585F **CT** / `fiberhome,hg5585f-ct` | FiberHome HG5585F **CU** / `fiberhome,hg5585f-cu` |
| `ethernet@4`（lan1 专用 MAC） | `okay`，2500base-x，netdev=lan1，phy-handle→phy@7 | `disabled`（无 phy-mode/netdev/phy-handle） |
| `mdio/ethernet-phy@7`（GPY211C） | **存在**：`ethernet-phy-id67c9.de10`，pin34 复位 | **不存在** |
| `pcs@1fa09000` | `okay` | 无 `status`（关） |
| `switch ports/port@1` + `phy@9` | `disabled`（内建 PHY1 让位） | `okay`，`label="lan1"` |
| reset 键 / factory / UBI / LED | GPIO35 / 同 / 同 / 同 | GPIO35 / 同 / 同 / 同 |
| DTB 字节数 / 节点数 | 23,281 / 190 | 22,959 / 189 |

→ **整包只差"lan1 用哪个 PHY"这一条主线**（`分析/dtb-diff.txt` 全文只有这一组差异 + 由此引起的 phandle 位移）。

### 3.5 PR #34 的 GPY211C 修复是否已在发布包里？——**是**

四条独立证据（详见 `分析/pr34-check.txt`）：

1. **git**：`firmware/ponwrt-hg5585f` 里 `edaeeb3 (Merge pull request #34, 2026-10-16)`
   是 `5b12fdb (2026-10-17, 发布包 commit)` 的祖先；`git diff edaeeb3..5b12fdb -- target/linux/airoha/dts`
   为空，且 `5b12fdb..HEAD` 也为空 → 发布 commit 上的 CT dtsi **already** 是
   `compatible = "ethernet-phy-id67c9.de10"` + `reset-gpios = <&en7581_pinctrl 34 …>` + `&gdm4` 2500base-x。
   （局限：本地仓库浅克隆，graft 根就是 `edaeeb3`，看不到 PR 前父提交。）
2. **包内**：CT 包 DTB 里逐字存在 `ethernet-phy-id67c9.de10` 与 GPIO34 复位（§3.3）。
3. **元数据**：`r0-5b12fdb` + `profiles.json` 的 `git_commit=5b12fdb…`。
4. **外部**：PR #34 标题 *"airoha/an7581: pin the GPY211C PHY ID on FiberHome HG5585F-CT"*，
   diff 正是把 `"maxlinear,gpy211","ethernet-phy-ieee802.3-c45"` 改成 `"ethernet-phy-id67c9.de10"`
   ——<https://github.com/pbs05/ponwrt/pull/34>【社区/外部资料，未在本机复现】

> PR 的动机（warm reboot 时 C45 ID 探测撞上 PHY 仍在复位 → 绑定 Generic C45 PHY →
> lan1 NO-CARRIER 直到冷启动）出自 PR 描述与 dtsi 注释。【推断】该修复在 CT 真机上
> 是否消除"偶发 lan1 不亮"**未在本机验证**。

**反面对照**：【包内证据】QWRT 的 CT 包里 `ethernet-phy@7` 仍是旧写法
`compatible = "ethernet-phy-ieee802.3-c45"`，`reset-deassert-us=800000`——
即 QWRT 那个包**没有** PR #34 的修复（详见 §7）。

### 3.6 包内容以外的确认 / 未确认

- 【包内证据】两版内核字节相同、rootfs 只差 4 KiB → PON 栈（`airoha-xpon` /
  `airoha-pond` / `ponctl`）与 CU 现役系统同源，差别在板级文件。
- 【包内证据，2026-10-21 Lead 补充核验】CT sysupgrade 的 rootfs（FIT offset 5,931,008 /
  54,796,288 B）用 7-Zip 列 squashfs 得 1,992 个条目，`passwall` 159 / `xray` 13 /
  `sing-box` 14 / `hysteria` 5 / `geoview` 3 / `chinadns` 3 / `luci-app-passwall` 9；
  与 `v2026.10.18-2` 的 CU 包（1,982 条目，同样计数）一致 → **首版 CT 镜像没有缺代理组件**
  （详见 `02-物料与校验.md` §9.1）。
- 【本机记录】CU 机 2026-10-19 起在跑 ponwrt（未签名镜像）→ "未签名 ponwrt 能在这块
  AN7581 板上装起来"有先例；**CT 机上未验证**。
- 未做：逐文件 diff 两版 `/etc/board.d`、`/lib/upgrade/platform.sh`（只做了组件存在性核对）。

---

## 4. U-Boot 行为与进 recovery 的正确姿势

### 4.1 已确认的事实

- 【本机记录】CU 机的 U-Boot 镜像（`QWRT-分析/uboot-cu.bin`，768,912 B）字符表里含：
  `bootdelay=3`、`Hit any key to stop autoboot: %d`、`bootmenu_title=U-Boot HG5585F CU`、
  8 项 bootmenu（Boot system / Web recovery / TFTP 三种 / Show storage / Reboot）、
  `httpd_ipaddr=192.168.0.1`、`boot_recovery=httpd dhcp`、
  `boot_ubi=run boot_production ; echo System boot failed, starting Web recovery ; run boot_recovery`、
  **`Reset held: entering HTTP recovery`**、`Reset button read failed (%d)`、
  button 框架（`button_gpio` / `gpio-keys` / `gpio-keys-polled`）。
- 【本机记录】串口日志 `光猫-HG5585F/x8-20261019-124441.log` 实录：
  bootmenu 画面渲染 → `Hit any key to stop autoboot: 3 / 2 / 1` → UBI 读 ECC 错误 →
  `System boot failed, starting Web recovery`。**3 秒打断窗口是真实存在的。**
- 【社区/外部资料，未在本机复现】U-Boot 官方 README 写"上电约一秒后按住 Reset 进入
  Web 恢复页面"：<https://github.com/pbs05/uboot-an758x>
- 【本机记录】原 U-Boot env 里**没有 `check_buttons` 变量**（见 `QWRT-分析/QWRT-R26.10.18-分析报告.md` §4）。

### 4.2 一个被社区/旧报告混为一谈的矛盾

旧报告据"env 无 `check_buttons`"推出"reset 键在 U-Boot 里没有绑任何恢复动作"。
本次在**同一个 U-Boot 二进制**里找到 `Reset held: entering HTTP recovery` 与
`Reset button read failed` 字符串——说明按钮处理是**编进代码**的（U-Boot 自带 DTB /
板级代码），不是靠 env 的 `check_buttons`。

【推断】"按住 reset 进 recovery"与"env 无 check_buttons"**并不矛盾**，两者可以同时成立；
但**reset 键在 U-Boot 阶段到底按的是哪个 GPIO**（U-Boot 用自带 DTB，可能与内核 DTB
的 GPIO35 不同），**未在本机验证**——CT 机上请以"串口 3 秒打断"为第一手段。

### 4.3 2.5G 口在 U-Boot 阶段不可用（社区说法）

【社区/外部资料，未在本机复现】HG5585F-CT 刷 an7581 U-Boot 时**不要用 2.5G 口**
（U-Boot 没有 2.5G PHY 驱动），网线要插 LAN2/3/4 才能打开 `http://192.168.0.1`：
<https://www.right.com.cn/forum/archiver/tid-8491746.html>

【推断】这与包内事实自洽：CT 的 lan1 走**外置 GPY211C + 独立 MAC + 额外 PCS**
（§3.3），U-Boot 侧若要通它，得单独带 GPY211 驱动；而 CU 机的 U-Boot 是给 4×内建 PHY
准备的。**本次没有 U-Boot 的 DTB 可查（未从 fip 里解出），故仍属未验证。**

### 4.4 操作结论（保守版）

1. 第一次上电/写引导后：**网线插 LAN2/3/4**，浏览器开 `http://192.168.0.1`；2.5G 口只
   在系统起来后再用。
2. 回滚/救砖第一手段：**串口 3 秒窗口**（`Hit any key`）→ bootmenu → `2. Web recovery`。
3. 不要把"按住 reset 开机"当唯一保险；它可能可用，但**本机未验证**。
4. CT 与 CU 的 firstblock/preloader/fip **逐字节不同**（§2 表），不能混用。

---

## 5. WiFi / 光模块与 factory 的 1 MiB 转换

- 【包内证据】ponwrt 的 CT/CU DTB 都把 WiFi 校准与 PON 校准放在 **factory 卷**内：
  `calibration@0`（2 KiB，PON 校准）、`eeprom@1000`（**4 KiB，MT7916 EEPROM**）、
  `mac-address@2000`、`pon-serial@2010`、`device-serial@2020`。
  → 内核期望的 factory 布局只用到前 ~8 KiB，**1 MiB 的 factory 卷足够**。
- 【本机记录】原厂 `mtd13` factory 是 **3 MiB**，刷 ponwrt 前要转成 **1 MiB** 再写回；
  转换工具 `fiberhome-factory.exe`（物料 `物料/工具/`）。CU 机已按此流程做过。
- 【本机记录】CU 机实测 `dd if=/dev/ubi0_3 bs=4096 skip=1 count=1` 首两字节 = **`16 79`**
  （MT7916 EEPROM magic），与 QWRT 闭源 WiFi 驱动的 `10-mt7916-an-eeprom` 校验一致
  （见 `QWRT-分析/QWRT-R26.10.18-分析报告.md` §3.3）。**该实测在 CU 机上，CT 机未复现。**
- 【社区/外部资料，未在本机复现】"刷完没 WiFi = 没恢复校准分区；`mtd13` 需转换 1 MiB
  后恢复"：<https://www.right.com.cn/forum/archiver/tid-8489713.html?page=2>
- 【推断/提醒】factory 卷**只属于这台机器**（PON 校准与 WiFi EEPROM 与硬件绑定），
  跨机复制无效；CT 机必须现场备份自己的 `mtd13` 再转换。

---

## 6. 电信版（CT）上联通线的可行性

- 【包内证据】CT 与 CU 包**内核字节相同**、rootfs 只差 4 KiB、DTB 只在 lan1 通道上不同；
  PON 驱动/用户态同源 → "CT 硬件能不能跑联通 PON 配置"取决于**线路侧**，不取决于
  CT/CU 差异。CT 包 DTB 里 PON 相关节点（`ethernet@2`、`pcs@1fa08000`、`optical-front-end@51`）
  与 CU 包**完全相同**。
- 【推断】换线后要配的是：PON 制式（`epon-10g-1g` 等）、OAM operator（联通线路按 CU 机
  经验是 **CTC**）、**LOID**、以及 PPPoE 的 VLAN（CU 机现网是 **VLAN 995**，`pon0.995`）。
  **LOID 与 PPPoE 帐号是"线路侧参数"，可照 CU 档案的格式/取值复用**（同一家运营商同一
  局向的配置项基本一致）；但 `pon0.995` 的 VLAN 值属线路侧参数，CT 这条线仍要以实测为准。
  若注册不上，优先怀疑 VLAN/LOID 不匹配或 OLT 绑定了设备，而不是 CT/CU 差异（见上条）。
- 【社区/外部资料，未在本机复现】CT/电信版在联通宽带上的注册经验（改地区/手工配置；
  有说法称**上海联通不绑 MAC/SN**）：<https://www.right.com.cn/forum/thread-8412912-1-29.html>
- 【推断/硬性建议】**不要克隆 CU 现网机的 SN/MAC**。两台的 factory 身份各自独立；
  混用会让两条线互相打架，也让回滚变复杂。CT 的 PON SN / MAC 从它自己的 `mtd13` 备份里取。
- 失败兜底：保留原厂全分区备份 + 原厂固件通道；CT 原厂固件目前**没有公开下载**（§8）。

---

## 7. QWRT CT 包（当前主目标）

### 7.1 包内事实（本次直接解析）

| 项 | 值 |
|---|---|
| FIT | kernel-1 `ARM64 QWRT Linux-5.4.302` gzip 4,579,254 B @0x1000 / fdt-1 14,698 B @0x45f000 / rootfs-1 37,552,128 B @0x463000 / `config@1` |
| system | OpenWrt **25.12.3** `r7856-44e450dae4`，target `airoha/an7581` |
| 白名单 | `fiberhome,hg5585f-ct`, `fiberhome,hg5585f-ct-usb-sfp` |
| 签名 | **有 usign/ucert 签名**：`untrusted comment: signed by key 215087f5c3341288`、`Local build key`、`ucert` TLV（certtype/validfrom/expiresat/pubkey） |
| DTB | `model="FiberHome HG5585F CT"`、`compatible="fiberhome,hg5585f-ct",…`；`/ethernet@1fb50000/port@1` = `lan1` `phy-mode=2500base-x`；`/mdio@1fb5f01c/ethernet-phy@7` = **`ethernet-phy-ieee802.3-c45`**（旧写法）、`reset-gpios` pin 34、`reset-deassert-us=800000`；`/keys/reset` = **GPIO0**；LED 只有 5 个（含单个 `blue:usb-1`） |

### 7.2 能用的部分

- 【包内证据】原生 **CT** DTB：lan1 走 2500base-x + 外置 PHY（reset GPIO34），
  与 CT 硬件对得上（不像 ponwrt 的 CU 包会把 lan1 关掉）。
- 【本机记录】（`QWRT-分析/QWRT-R26.10.18-分析报告.md`，对同一包族的逆向）：
  PON 栈与 ponwrt 同源（`ponctl` 支持 `epon-10g-1g`，默认 `operator=ctc`）；
  无线是闭源 `mt7916_ap.ko` + `mtwifi`（`ra0/rai0`）；默认 LAN `192.168.1.1`；
  默认 `lan1` 当 WAN；包管 `opkg`；无 passwall（有 openclash / shadowsocksr / xray 二进制）。
  ⚠️ 这些是既有材料结论；本次只复核了 FIT/DTB/签名层。**rootfs 默认配置已由 Lead 拆包核对**（QWRT `02_network`：lan1=WAN、lan2-4=LAN；LAN 192.168.1.1；root/`password`；Telnet 默认开；WiFi 默认 `encryption=none`；PON `mode` 空/`ctc`/`ge_ports=1`；无 Passwall；feeds 首启被改成 ImmortalWrt 24.10.6），详见 `08-QWRT刷机流程.md`。

### 7.3 代价 / 不建议作为首选的原因

1. **内核 5.4.302 老 BSP**，而 ponwrt CT 是 6.18.55；两套驱动/调优经验不能直接搬。
2. **DTB 是 PR #34 之前的版本**：`ethernet-phy-ieee802.3-c45` + 800 ms 复位 → 正是
   PR #34 描述的那种"warm reboot 偶发 lan1 NO-CARRIER"风险形态【推断，未实机验证】。
3. **reset 键指到 GPIO0**，而 ponwrt 的 CT/CU DTB 都是 GPIO35 → 该包的内核侧按键
   定义与板子对不上（U-Boot 侧未知）。
4. 默认 `lan1=WAN` + LAN `192.168.1.1`，与家宽 `192.168.31.0/24`、光猫 `192.168.1.1`
   都冲突，刷完必须离线改网段。
5. 无 passwall（现网代理栈是 Passwall/xray），要重建分流方案。
6. **只有 CT 包**（本目录/发布页都未见 CU 版），生态上属于"备选、非主线"。

**结论【推断】**：QWRT CT 在 CT 硬件上原生可用；如果选它，要接受“老内核 + 旧 PHY 写法 + 按键 GPIO 不符 + 无 passwall + 默认开放 WiFi/默认 lan1=WAN”这些代价，操作与规避见 `08-QWRT刷机流程.md`。它更适合“WiFi/2.5G 优先”的场景，不适合“原样复刻现网 Passwall”的场景。

---

## 8. 未解问题清单（按优先级）

| # | 问题 | 现状 | 怎么解 |
|---|---|---|---|
| 1 | **CT 版原厂「一键刷入包」（Ubi-Update）不存在** | 工作区只有 CU 版 `Fh-HG5585F-Ubi-Update-1h-V260921-*.bin`；CT 版要问卖家/QQ 群 | 拿到后放 `物料/工具/` 并登记哈希；拿不到就走 Telnet/TTL + `an758x-stock2ubi` |
| 2 | **CT 实际 PON 制式未知**（EPON_10G / GPON / XGPON） | 未通电采集；`00-开始这里.md` 已把它列为刷前必查项 | 原厂后台 `/fh_tool/api` 的 `GetDevInfo.current_ponmode`；若 GPON，ponwrt 的 AN7581 GPON 驱动未实现，**先停** |
| 3 | **U-Boot 阶段 reset 键是否真能进 recovery** | 只有 CU U-Boot 二进制的字符串（`Reset held: entering HTTP recovery`）+ 官方 README 说法；**未实测** | CT 机接串口，分别试"上电 1 秒内按住 reset"和"3 秒内按任意键"，记录哪种进 bootmenu |
| 4 | **U-Boot 阶段 2.5G 口是否真的不通** | 社区说法（tid-8491746）；本次没解 U-Boot 的 DTB，无法证实 | 插 LAN1 试 `http://192.168.0.1`（预期不通），同时用 LAN2 验证；不要以此判断"砖" |
| 5 | **CT 原厂固件回滚路径** | 官方不公开；只能靠刷前全分区备份 | 备份 `mtd0..mtd16` + UBI 卷；确认 `mtd13` factory 3 MiB 备份完整（PON 校准 + WiFi EEPROM 唯一来源） |
| 6 | QWRT/ponwrt 两版 DTB 的 reset 键 GPIO（0 vs 35）哪个是板子真实接法 | 包内证据互相矛盾；CU 机实际记录支持 35 | CT 机上 `cat /proc/bus/input/devices` + 按 reset 看 `evtest`，或直接看按键是否触发 `KEY_RESTART` |
| 7 | ponwrt 包尾 16 字节 `FWx0` 段头的字段语义 | 只能确定首 4 字节是 ASCII `FWx0`、后 4 字节随包变化；QWRT 签名包在同一位置后又跟 usign 文本与 ucert TLV，但字段定义**未用官方 `fwtool` 核对** | 拿 `fwtool` 源码/二进制核对该段；对刷机无影响 |
| 8 | CT 版 v2026.10.18 是否就是最后一个含 CT 的 release | 物料里 `v2026.10.18`(5b12fdb) 有 CT+CU；`v2026.10.18-2`(e585ae8) **只有 CU** | 关注发布页；若 CT 需要 -2 的 CI 修复，得等/自编 CT 包（本次未评估 CT rootfs 组件完整性） |
| 9 | CT 机 rootfs 内部与 CU 包的具体差异（逐文件 `/etc/board.d`、`/lib/upgrade/platform.sh`） | 只做了组件存在性核对：Passwall/Xray/Sing-Box/Hysteria/Geoview/chinadns 均在（`02` §9.1） | 用 `unsquashfs` 解 CT rootfs 后逐文件 diff |

---

## 附：社区/外部资料一览（全部"未在本机复现"）

1. 恩山：HG5585F-CT 刷 an7581 U-Boot **不要用 2.5G 口**（U-Boot 无 2.5G PHY 驱动）
   <https://www.right.com.cn/forum/archiver/tid-8491746.html>
2. 恩山：刷后没 WiFi = 没恢复校准分区，`mtd13` 需转换 **1 MiB** 后恢复
   <https://www.right.com.cn/forum/archiver/tid-8489713.html?page=2>
3. 恩山：CT/电信版在联通宽带上的注册经验（改地区/手工配置；上海联通据称不绑 MAC/SN）；
   同帖还有烽火隐藏账户/工厂 CLI 步骤（`admin` / `Fh@+MAC后六位`、`touch /var/fhconfig`、
   `fiberhomehg2x0/zgjt`、`load_cli factory` → `show admin_name` / `show admin_pwd`）
   <https://www.right.com.cn/forum/thread-8412912-1-29.html>
4. `pbs05/uboot-an758x`：手动路径（写 firstblock/preloader，BL2 请求 FIP 时按 `x` 走 XMODEM）、
   "上电约一秒后按住 Reset 进 Web recovery" <https://github.com/pbs05/uboot-an758x>
5. `pbs05/an758x-stock2ubi`：`:3333` 页面备份 + 刷引导；必须 root 运行；telnet 空闲会退出
   <https://github.com/pbs05/an758x-stock2ubi>
6. `pbs05/fiberhome-factory`：GUI 工具，把原厂 3 MiB `mtd13` 转成 OpenWrt 用的 1 MiB 布局
   <https://github.com/pbs05/fiberhome-factory>
7. `pbs05/ponwrt`（上游）<https://github.com/pbs05/ponwrt> ｜
   PR #34（GPY211C PHY ID）<https://github.com/pbs05/ponwrt/pull/34>
8. 本工作区内的**非本次实测**材料（供追溯，不要当"本次证据"）：
   `QWRT-分析/QWRT-R26.10.18-分析报告.md`（QWRT 包逆向、CU 机实测记录）、
   `光猫-HG5585F/downloads/刷机物料-20261019.md`（CU 包哈希与刷机物料）、
   `光猫-HG5585F/serial-ont-*.log` / `x8-*.log`（CU 刷机串口实录）。
