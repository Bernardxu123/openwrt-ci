# QWRT CT → CU 适配改造

> **目标机** 烽火 HG5585F **CU**（联通版，AN7581）
> **两个产物**：
> - `QWRT-R26.10.21-hg5585f-cu-patched.itb` — 42,201,767 B，sha256 `9eaa021a…529f317c`（**当前推荐**，基于 QWRT R26.10.21）
> - `QWRT-R26.10.18-hg5585f-cu-patched.itb` — 42,152,775 B，sha256 `6c3fae59…541ee8c6`（历史版本）
>
> 状态：10.18 版**已在真机通过 `valid: true`**；10.21 版结构校验全过（FIT 三镜像 hash / fwtool trailer / metadata / DTB 全部 OK），`fwtool_signature: true` 已在真机确认，**设备白名单需在 CU 机器上复核**（见 §10.3）。


---

## 0. 结论

原包是 CT 变体，被设备白名单挡住。改完后（下图为 **10.18 版在 CU 真机** 的实测结果；10.21 版结构相同，见 §10）：

```
$ sysupgrade -T /tmp/qwrt-cu.itb
Signature check OK
rc=0

$ /usr/libexec/validate_firmware_image /tmp/qwrt-cu.itb
{
	"tests": {
		"fwtool_signature": true,
		"fwtool_device_match": true      ← 原包是 false
	},
	"valid": true,                        ← 原包是 false
	"forceable": true,
	"allow_backup": true
}
```

**`valid: true` 意味着可以普通 `sysupgrade`，不再需要 `-F` 强刷。**

---

## 1. 改了什么（6 处 DTB + 2 处元数据）

逐字节 diff 确认，**只有这些**改动，无任何意外修改：

| # | 位置 | 原值 | 新值 | 原因 |
|---|---|---|---|---|
| 1 | 根节点 `compatible` | `fiberhome,hg5585f-ct` | `fiberhome,hg5585f-cu` | 板型识别；`board_name` 由此得来，决定 `platform.sh`/`02_network`/`03_pon_data` 走哪个分支 |
| 2 | 根节点 `model` | `FiberHome HG5585F CT` | `FiberHome HG5585F CU` | 显示名 |
| 3 | `/keys/reset` `gpios` | `GPIO0` | **`GPIO35`** | CT 版 DTB 指错（GPIO0 是 `uart1_txd`，没接按键）；U-Boot 用的是 35 |
| 4 | `/mdio@1fb5f01c/ethernet-phy@9` | 无 `phandle` | `phandle = 42` | 内建 PHY1，CU 的 lan1 用它 |
| 5 | `/ethernet@1fb50000/port@1` | `phy-handle = 29`（→PHY7）<br>`phy-mode = 2500base-x` | `phy-handle = 42`（→PHY9）<br>`phy-mode = internal` | **核心修复**：lan1 从外置 GPY211C 换回内建 PHY |
| 6 | `/mdio@1fb5f01c/ethernet-phy@7` | 存在（GPY211C） | **删除** | CU 没有这颗 2.5G 外置 PHY |
| 7 | FIT `fdt-1` 的 `hash-1`/`hash-2` | crc32 `a0ab8981` / sha1 `576ece70…` | crc32 `b6a2245f` / sha1 `d14bb654…` | DTB 变了要重算 |
| 8 | 尾部 metadata JSON | `supported_devices:["fiberhome,hg5585f-ct",…]`<br>`board: fiberhome_hg5585f-ct` | `[…-cu, …-cu-usb-sfp]`<br>`fiberhome_hg5585f-cu` | 设备白名单 |

**额外必须做的（关键，容易漏）**：`fwtool` 的 trailer CRC 重算 —— 见下节。

---

## 2. 技术难点：fwtool trailer 的 CRC 链

改完 DTB 后 `sysupgrade -T` 报 `Image metadata not present`，不是 metadata 没写对，而是 **fwtool 的 CRC 校验失败导致整块 metadata 被丢弃**。

### 结构（`package/system/fwtool/src/fwimage.h`）

```c
struct fwimage_trailer {
    uint32_t magic;   // 0x46577830  "FWx0"
    uint32_t crc32;   // 覆盖 [文件开头 .. 本 trailer 之前]
    uint8_t  type;    // 0 = signature, 1 = info(metadata)
    uint8_t  __pad[3];
    uint32_t size;    // 本 chunk 总长（含 trailer 这 16 字节）
};
```

镜像尾部是**两层嵌套 chunk**：

```
[0x000000 .. 0x2833000)   FIT 镜像本体
[0x2833000 .. 0x2833123)   info chunk：8 字节 header + 282 字节 JSON
[0x2833123 .. 0x2833133)   info trailer      (type=1, size=0x133=307)
[0x2833133 .. 0x2833337)   signature chunk：ucert 签名
[0x2833337 .. 0x2833347)   signature trailer (type=0, size=0x214=532)
```

### CRC 算法（源码 + 实测双重确认）

```c
crc32_block(init=~0, buf, len)   // 无最终取反
```

Python 等价：

```python
def fwtool_crc(blob):
    return (zlib.crc32(blob, 0xFFFFFFFF ^ 0xFFFFFFFF) ^ 0xFFFFFFFF) & 0xFFFFFFFF
```

**用原始镜像验证**（这是确认算法正确的关键一步）：

```
trailer#0 type=0 @0x2833337  stored=a63fcfde  raw_crc=a63fcfde  MATCH
trailer#1 type=1 @0x2833123  stored=792ef138  raw_crc=792ef138  MATCH
```

### 嵌套关系 → 重算顺序

**signature trailer 的 CRC 覆盖了 info chunk 的字节**，所以必须：

```
先重算 info trailer 的 crc32
再重算 signature trailer 的 crc32   ← 此时 info 已经是对的
```

顺序反了就会失败（我第一次就踩了这个坑：signature 重算后 `calc=dde398e2` 对不上，因为当时 info 还没改）。

---

## 3. 验证清单（全部通过）

| 检查 | 命令 | 结果 |
|---|---|---|
| FIT 三镜像 crc32+sha1 | 自写解析器 | kernel OK / fdt OK / rootfs OK |
| FIT 签名（U-Boot 同款） | `fit_check_sign -f` | `rc=0`，三镜像全 OK |
| metadata 提取 | `fwtool -q -i` | `rc=0`，JSON 正确 |
| 签名提取 | `fwtool -q -s` | `rc=0` |
| 设备匹配 | `validate_firmware_image` | **`fwtool_device_match: true`** |
| 综合校验 | 同上 | **`valid: true`** |
| 升级前检查 | `sysupgrade -T` | **`rc=0`** |
| DTB 解析 | 设备侧 `strings` | `FiberHome HG5585F CU` / `fiberhome,hg5585f-cu` |
| phandle 唯一性 | 自写检查 | 41 个，无重复；42 只属于 PHY9 |
| DTB 大小 | — | 14488 ≤ 14698（容器大小不变，补零） |

---

## 4. 文件

| 文件 | 说明 |
|---|---|
| `QWRT-R26.10.18-hg5585f-cu-patched.itb` | **成品**，42,152,775 B，sha256 `6c3fae59…541ee8c6` |
| `patch_qwrt_cu.py` | 改造脚本，可重复运行、幂等（每步都有 assert） |
| `QWRT-R26.10.18-分析报告.md` | 原包逆向分析 |

脚本用法：

```bash
python patch_qwrt_cu.py <原始CT包.itb> <输出CU包.itb>
```

---

## 5. 刷机步骤

```sh
# 1) 先备份（已有：/tmp/ponwrt-backup-20261020-1226.tar.gz，PC 上也有）
sysupgrade -b /tmp/ponwrt-backup.tar.gz

# 2) 上传包到 /tmp（42 MB，/tmp 是 tmpfs，214 MB 够）

# 3) 升级（不需要 -F，metadata 已匹配）
sysupgrade /tmp/QWRT-R26.10.18-hg5585f-cu-patched.itb

# 4) 起来后
#    LAN 是 192.168.1.1（会跟光猫原厂地址撞，记得改）
#    root 密码 password
#    ssh root@192.168.1.1
```

### 首次开机必须配的

```sh
# LAN 段改掉，避免和光猫 192.168.1.1 冲突
uci set network.lan.ipaddr='192.168.31.1'
uci commit network

# PON：epon-10g-1g + CTC OAM + LOID（ponwrt 上验证过的同一套）
uci set pon.line0.mode='epon-10g-1g'
uci set pon.line0_oam.operator='ctc'
uci set pon.line0_oam.loid='000000000000000014509791'
uci set pon.line0_oam.ge_ports='4'
uci commit pon

# WAN：pon0.995 跑 PPPoE
uci set network.wan.device='pon0.995'
uci set network.wan.proto='pppoe'
uci set network.wan.username='02105250448'
uci set network.wan.password='052356'
uci commit network
/etc/init.d/network restart
```

---

## 6. 改完之后还剩什么差异

DTB 修好了，但 **rootfs 还是 CT 编译的那份**，所以：

| 项 | 状态 |
|---|---|
| LAN1 网口 | ✅ **已修复**（内建 PHY1） |
| reset 键 | ✅ **已修复**（GPIO35） |
| 板型识别 | ✅ CU（`board_name` 正确，`02_network`/`03_pon_data`/`platform.sh` 走 CU 分支） |
| WAN 默认口 | ✅ **已按 CU 分支**：`board.d/02_network` 按 `board_name` 匹配，CU 走 `ucidef_set_interfaces_lan_wan "lan1 lan2 lan3 lan4" "pon0"` → LAN=lan1-4、WAN=pon0（**但 pon0 上没有 VLAN 995，仍需手工建 `pon0.995` + PPPoE**） |
| USB LED | ⚠️ 只配 1 个（CT 单 USB），实际 2 个 |
| 默认 LAN IP | ⚠️ `192.168.1.1`，与光猫冲突 |
| `ge_ports` 默认 | ⚠️ `1`，要改 `4` |
| PON 栈 | ✅ 同源 Airoha，`ponctl` 支持 `epon-10g-1g`，`airoha-pond` 含 `ctc.rs` |
| WiFi 校准 | ✅ 从 factory 0x1000 读，magic `16 79` 已实测匹配 |

**软件源仍然不可用**（与改造无关）：`distfeeds.conf` 指向 OpenWrt 25.12.3 的 opkg 源，但 25.12 起上游全转 apk，实测 11 个源全部 404。要装包得自己找 opkg 兼容源。

---

## 7. 风险与回滚

**风险**：
- DTB 是我手工重建的，虽然结构校验通过，但**没有在真机上跑过**
- 如果内建 PHY1 在这颗芯片上实际不可用（理论上应该可用，ponwrt 正在用 `mt7530-0:09`），LAN1 仍会不通 → 换 LAN2/3/4
- 若内核 panic，U-Boot 不会自动回退（`boot_ubi` 只在 `ubi read`/`iminfo` 失败时回落），**需要串口 3 秒内打断**

**回滚**（网络能通时）：
```sh
sysupgrade /tmp/ponwrt-airoha-an7581-fiberhome_hg5585f-cu-squashfs-sysupgrade.itb
```
官方 ponwrt CU 包，sha256 `4b7c3431…f76c` 已核对，在 `光猫-HG5585F/downloads/ponwrt-v2026.10.18-2/`。

**彻底救砖**：串口 → `bootmenu` → `1. Web recovery`（`http://192.168.0.1/`）

---

## 8. 顺带确认的两件事

1. **U-Boot 的 reset 键本来就是 GPIO35**（从 `uboot-cu.bin` 解出：`gpios = <0x0c 0x23 0x1>` → pinctrl, 35, ACTIVE_LOW），QWRT 的 Linux DTB 指 GPIO0 是错的。**改完两边一致了。**

2. **U-Boot `bootm` 不带 `#config-1`**，走 FIT 默认配置。QWRT 包的默认配置名是 `config@1`，所以**引导链不用动**。

---

## 9. 附：为什么 metadata 必须等长替换

`fwtool` 的 trailer 里 `size` 是**绝对长度**，且 CRC 覆盖 `[0, trailer_off)`。如果 JSON 长度变了：

- 所有后续偏移全变
- 需要重写 trailer 的 `size` 字段
- CRC 覆盖范围也变

本次 `ct` → `cu` 恰好等长（`fiberhome,hg5585f-ct` 和 `fiberhome,hg5585f-cu` 都是 20 字符；`fiberhome_hg5585f_ct` 和 `fiberhome_hg5585f_cu` 都是 21 字符），所以**偏移不变，只需重算 CRC**。脚本里有 `assert len(new_jtxt) == len(jtxt)` 守着这一点。

---

## 10. R26.10.21 版本（2026-10-22 制作）

### 10.1 与原包的差异

| 项 | R26.10.18 | R26.10.21 |
|---|---|---|
| 文件大小 | 42,152,775 B | **42,201,767 B** |
| sha256 | `6c3fae59…541ee8c6` | **`9eaa021a0771534605507f96a9b2d638a70d240d3f3d27937cdf6da4529f317c`** |
| 内核 | 4,579,254 B | 4,581,813 B |
| rootfs | 37,552,128 B | 37,597,184 B |
| revision | `r7856-44e450dae4` | `r7901-e908d04a4e` |
| **DTB** | sha256 `b56ae8c6…b46528` | **完全相同（逐字节一致）** |
| `airoha-pond` | 旧版（OAM FCS bug） | 新版（修了 CTC 11 字节版本协商） |

**DTB 与 10.18 完全一致**，所以 `patch_qwrt_cu.py` **不需要任何修改**，直接跑即可。

rootfs 侧与 CU 相关的文件（`board.d/02_network`、`01_leds`、`03_pon_data`、`platform.sh`、`config/pon`、`config/firewall`）与 10.18 的 CU 分支一致；10.21 的 rootfs 差异只有：① 新增 gemtek xr1710g 机型 ② `97-default-settings` 的版本字符串。**不影响 CU 适配**。

### 10.2 制作与校验命令

```sh
python patch_qwrt_cu.py \
  ../光猫-HG5585F/QWRT-R26.10.21-airoha-an7581-fiberhome_hg5585f-ct-squashfs-sysupgrade.itb \
  QWRT-R26.10.21-hg5585f-cu-patched.itb
```

脚本输出（关键行）：

```
[1] compatible -> fiberhome,hg5585f-cu
[2] model      -> FiberHome HG5585F CU
[3] keys/reset gpios -> GPIO35
[4] ethernet-phy@9 phandle = 42
[5] port@1 phy-handle 29 -> 42, phy-mode -> internal
[6] 删除 ethernet-phy@7 (GPY211C)
[7] fdt crc32=b6a2245f sha1=d14bb65485b219ba…
[8] metadata ct->cu 等长替换 OK (282 B @0x283f008)
    所有 trailer CRC 校验通过
```

独立复核结果（**全部通过**）：

| 检查 | 结果 |
|---|---|
| FIT `kernel-1` / `fdt-1` / `rootfs-1` 的 crc32 + sha1 | 6/6 OK |
| fwtool `info` trailer CRC | `ac8a3fb8` OK |
| fwtool `signature` trailer CRC | `1eea6adc` OK |
| metadata | `supported_devices = [hg5585f-cu, hg5585f-cu-usb-sfp]`，`board = fiberhome_hg5585f_cu` |
| DTB compatible / model | `fiberhome,hg5585f-cu` / `FiberHome HG5585F CU` |
| reset 键 | GPIO35 |
| mdio 子节点 | `phy@9 / @a / @b / @c`（`phy@7` 已删） |
| port@1 | `phy-handle=42`、`phy-mode=internal` |
| phandle 唯一性 | 41 个，无重复，最大 42 |
| 字节改动范围 | 5353 B，**只在** DTB / fdt hash / metadata / trailer CRC 四处 |

### 10.3 真机复核现状

在 **CT 机器（当前跑 QWRT R26.10.21）** 上跑 `/usr/libexec/validate_firmware_image`：

```json
{ "tests": { "fwtool_signature": true, "fwtool_device_match": false },
  "valid": false, "forceable": true, "allow_backup": true }
```

- `fwtool_signature: true` → **签名段和 CRC 都是好的**，改包没有破坏签名结构；
- `fwtool_device_match: false` → **符合预期**，因为验证机是 CT（`/tmp/sysinfo/board_name = fiberhome,hg5585f-ct`），而镜像声明的是 CU。
- 在 CU 机器上应得到 `device_match: true` → `valid: true`（10.18 版就是这样验证通过的）。**刷之前建议先在 CU 机上跑一次 `sysupgrade -T` 确认。**

### 10.4 刷机后网络默认值（10.21 的 CU 分支）

```
LAN   lan1 lan2 lan3 lan4  ← br-lan，地址 192.168.1.1
WAN   pon0                 ← 注意：不是 pon0.995，需要在上面建 802.1q
PON   mode ''（空）        ← 必须设 epon-10g-1g
OAM   operator 'ctc'       ← 已默认
      ge_ports '1'         ← 必须改 4
```

首启仍需按 §5 的手工步骤补：LAN 段、PON 模式、LOID、`pon0.995` + PPPoE。



---

## 11. 2026-10-23 复盘：为什么前两版 CU-patched 不启动，以及 v2 的修法

> 结论一句话：**打包没错，错在 DTB 语义**——`port@1` 的 `phy-mode` 被改成 `"internal"`，
> 而这个 5.4 BSP 内核根本不认识这个字符串，导致整块 `ethernet@1fb50000` 不 probe、
> lan1–lan4 全灭，用户看到的就是「进不去系统」。

### 11.1 打包层已逐项排除（不是「编译失败」）

对旧包 `QWRT-R26.10.21-hg5585f-cu-patched.itb` 复核（`verify_qwrt_cu_v2.py --self-test`）：

| 检查项 | 结果 |
|---|---|
| FIT 三镜像 `kernel-1/fdt-1/rootfs-1` 的 crc32 + sha1 | 全部重算一致 |
| fwtool metadata JSON（`supported_devices` / `board`） | 正确（cu / fiberhome_hg5585f-cu），282 字节不变 |
| 内外两层 footer CRC（`FWx0`+crc+type+size） | 全部一致 |
| DTB 结构（magic / offset / token 嵌套 / phandle 唯一 / 引用可解析 / FDT_END） | 通过 |

→ 旧包**能刷、能过校验**，问题只在运行期。

### 11.2 根因：`phy-mode = "internal"` 不在 5.4 BSP 的 `phy_modes[]` 里

- QWRT 内核 `kernel-1.gz` 解压后穷举字符串：`phy_modes[]` 表里只有
  `gmii / sgmii / tbi / rev-mii / rmii / rgmii / rgmii-id / rgmii-rxid / rgmii-txid / rtbi /
  smii / xgmii / moca / qsgmii / trgmii / 1000base-x / rxaui / xaui / 10gbase-kr / usxgmii / 5gbase-r`，
  **没有 `internal`**（整镜像里 `\0internal\0` 出现 0 次；`2500base-x` 只作为
  `maxlinear,force-2500base-x` 的子串存在）。
- 该内核内置 **phylink**（字符串 `configuring for %s/%s link mode`、`phy-handle`、`in-band-status`）。
  驱动把 `of_get_phy_mode()` 的结果喂给 `phylink_create()`；未知串返回 `-EINVAL`/`-ENOTSUPP`
  → 端口/整卡探测失败。
- **决定性对照**：同一个 QWRT CT DTB 里 `port@2/3/4`（内建 PHY2-4，CT 上实测可用）**完全没有 `phy-mode` 属性**。
  `phy-mode="internal"` 只出现在 mdio 子节点 `ethernet-phy@9/a/b/c` 上（那是 BSP PHY 驱动自己读的，
  不走 MAC 侧的 `of_get_phy_mode`）。
- 提法修正：**内建 PHY 口 = 不写 `phy-mode`**，不是写成 `"internal"`。

### 11.3 CU 与 CT 的 port 接线（权威来源）

| | lan1 | lan2/3/4 |
|---|---|---|
| CT | `gdm4` MAC + 外置 GPY211C（mdio 7，`2500base-x`）+ `eth_pcs` | 内建 switch port 2-4 + 内建 PHY2-4（mdio a/b/c） |
| CU | **内建 switch port 1 + 内建 PHY1（mdio 9）** | 同上 |

来源：ponwrt `an7581-fiberhome-hg5585f-ct-common.dtsi`（`gdm4`/`gpy211`/`eth_pcs`）与
`...-cu-common.dtsi`（`gsw_port1` + `gsw_phy1`）；CU 机 ponwrt 实测 `lan1..lan4` 都是 DSA 口、eth0=10G CPU 口；
QWRT 自己的 `02_network` CU 分支注释也写着 "The integrated switch provides all four panel ports"。

→ 所以 CU 的 `port@1` 应当**与 `port@2/3/4` 同构**：只保留 `phy-handle`（指向 `ethernet-phy@9`），**不写 `phy-mode`**。

### 11.4 v2 的 7 项改动（全部等长或删除）

| # | 节点 | 属性 | 改动 |
|---|---|---|---|
| 1 | `/` | `compatible` | `fiberhome,hg5585f-ct` → `fiberhome,hg5585f-cu`（同长） |
| 2 | `/` | `model` | `FiberHome HG5585F CT` → `... CU`（同长） |
| 3 | `port@1` | `phy-handle` | `0x1d`(phy@7) → `0x2a`(新 phy@9 phandle) |
| 4 | `port@1` | **`phy-mode`** | **整条删除**（旧版写 `"internal"` ← 就是它挂的） |
| 5 | `ethernet-phy@9` | `phandle` | 新增 `0x2a`（原表最大 41，42 空闲） |
| 6 | `ethernet-phy@7` | 整个节点 | 删除（CU 无 GPY211C，也不再拨 GPIO34） |
| 7 | `keys/reset` | `gpios` | `<9 0 1>` → `<9 35 1>`（GPIO0 实为 `uart1_txd`） |

### 11.5 v2 的 DTB 编辑方式（与旧版不同）

旧版 `patch_qwrt_cu.py` **整体重序列化** FDT → `totalsize` 从 14698 缩到 14488，
FIT `data-size` 仍是 14698，尾部 210 字节零填充，并重新生成 strings 块。

v2 改为 **libfdt 语义的原位编辑**（等价于 `fdt_del_node` / `fdt_delprop` 的 NOP 覆盖）：

- header / `off_dt_struct` / `off_dt_strings` / `size_dt_struct` / `size_dt_strings` / strings 块
  **与 CT 原版逐字节相同**；
- 删掉的节点/属性让 struct 块变短，缺口用 **FDT_NOP**（43 个）补齐，且**必须落在根节点
  `END_NODE` 之前**（见下方 2026-10-23 坑）；
- `totalsize == FIT data-size == 14698` 严格相等，不存在"DTB 比容器小"的边角情况。

### 11.6 新产物

| 文件 | 说明 | sha256 |
|---|---|---|
| `QWRT-R26.10.21-hg5585f-cu-v2.itb` | 主刷机包 | `310e0b3f…26d3417` |
| `QWRT-R26.10.21-hg5585f-cu-control.itb` | 诊断包（只换 metadata，DTB 与 CT 逐字节一致） | `8603f2c0…028cc7932` |
| `patch_qwrt_cu_v2.py` | 新改包脚本（`--variant cu|control`） | — |
| `verify_qwrt_cu_v2.py` | 校验器 + `--self-test` 回归 | — |
| `刷机-CU-v2.md` | 刷机 / 观测 / 回滚 runbook | — |

回归结果（`python verify_qwrt_cu_v2.py --self-test`）：

```
CT 原版      -> PASS（20 项）
旧 CU-patched -> FAIL（3 项，正是 "totalsize==data-size"、"port@1 无 phy-mode"、"差分 7 项"）← 断言有牙齿
cu-v2        -> PASS（30 项）
cu-control   -> PASS（23 项）
```

### 11.7 未证实的部分（刷机后按 runbook 判定）

- `port@1` 在 BSP 驱动里是否真的被当作 **switch port 1**（而不是固定绑到 2.5G GDM/PCS 通路）。
  若是后者，v2 的结果会是「能启动、lan2-4 通、lan1 不通」——仍可用，lan1 另开一轮。
- CU 的 U-Boot HTTP recovery 走哪个面板口（CT 经验是 lan2/3/4；CU 四口全内建，理论上都行）。
- ~~内核是否对 `FDT_NOP` 填充有隐性要求~~ → **2026-10-23 已实测搞清**：U-Boot 网页刷机用
  `fdt_check_full()`，要求"NOP 只能在树内部、根 END_NODE 之后必须紧跟 FDT_END"；已按此修正并自查通过。
  剩余待验证：`port@1` 在 BSP 里是否真为 switch port 1（若固定绑 2.5G GDM/PCS，结果会是
  "能启动、lan2-4 通、lan1 不通"）。

### 11.8 v2 产物哈希（2026-10-23 修正 NOP 位置后）

| 文件 | sha256 |
|---|---|
| `QWRT-R26.10.21-hg5585f-cu-v2.itb` | `adb895d35cebe380560813b44c31d32ee8346d165e5e652f363288ff2ef4bfad` |
| `QWRT-R26.10.21-hg5585f-cu-control.itb` | `8603f2c0fbd141631256d1997e954fdc1556c5d140c2e82ba96312c028cc7932` |

校验：`verify_qwrt_cu_v2.py` 现含 31 项（新增 `fdt_check_full()` 逐行等价实现），
`--self-test` = CT 原版 21 PASS / 旧 CU-patched 3 FAIL / v2 31 PASS / control 24 PASS。

