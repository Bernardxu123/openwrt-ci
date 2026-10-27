# QWRT R26.10.21 → CU（HG5585F）刷机 / 观测 / 回滚 runbook

> 生成时间：2026-10-23
> 适用机：**CU 版 HG5585F**（联通，AN7581，4 个内建 PHY 口），当前跑 ponwrt，LAN `192.168.1.1`，密码 `Qazswxdecf1`
> ⚠️ **不要碰 CT 生产机（192.168.31.1）**；本流程只对 CU 实验机操作。

---

## 0. 产物

| 文件 | 用途 | 大小 | sha256 |
|---|---|---|---|
| `QWRT-R26.10.21-hg5585f-cu-v2.itb` | **主刷机包**（CU 全功能） | 42,201,767 | `adb895d35cebe380560813b44c31d32ee8346d165e5e652f363288ff2ef4bfad` |
| `QWRT-R26.10.21-hg5585f-cu-control.itb` | 诊断包（只换 metadata，DTB 与 CT 逐字节一致） | 42,201,767 | `8603f2c0fbd141631256d1997e954fdc1556c5d140c2e82ba96312c028cc7932` |
| `..\光猫-HG5585F\downloads\ponwrt-airoha-an7581-fiberhome_hg5585f-cu-squashfs-sysupgrade.itb` | **回滚包**（当前在跑的系统） | — | — |

现场只用主刷机包；control 包只在 v2 失败后才用。

---

## 1. 刷机前 60 秒检查

1. PC 以太网仍是 `192.168.1.106/24`，网线插在 CU 机的 **lan2**（当前就是这根）。
2. `ping 192.168.1.1` 通 → 打开 `http://192.168.1.1`，`root` / `Qazswxdecf1` 能进 LuCI。
3. 记下 LuCI 里 `状态 → 概览` 的 `PonWrt SNAPSHOT r0-e585ae8`（确认还是 ponwrt，没跑错机）。
4. 确认回滚包在本机可访问（上表第 3 行路径）。
5. 手边能按到 CU 机的 reset 键（GPIO35）。

---

## 2. 刷入（推荐：LuCI）

1. LuCI → **系统 → 备份/刷机（Backup / Flash Firmware）**。
2. `刷写新固件` 处选择 `QWRT-R26.10.21-hg5585f-cu-v2.itb`。
3. **取消勾选「保留配置 / Keep settings」**（ponwrt 的配置不能带进 QWRT）。
4. 点「刷入固件」→ 确认。等待 2–4 分钟（自动重启）。

> 该路径会走 ponwrt 的 `platform_check_image`（FIT 三镜像 crc32/sha1）与 `fwtool_check_image`
> （`supported_devices` 已含 `fiberhome,hg5585f-cu`）；ponwrt 未设 `REQUIRE_IMAGE_SIGNATURE`，
> 签名不参与校验。若被拒，直接走 §3。

---

## 3. 兜底刷入（U-Boot HTTP recovery，绕过所有校验）

1. 断电 → **按住 reset 键** → 上电 → 继续按住 5–8 秒（U-Boot 打印 `Reset held: entering HTTP recovery`）。
2. PC 网卡改静态：IP `192.168.0.10`，掩码 `255.255.255.0`，**网关/DNS 留空**。
3. 浏览器开 `http://192.168.0.1` → `Install system`（或 `刷写系统`）→ 选 `.itb` → 上传并刷入。
4. 若 lan2 打不开，换 **lan3 / lan4** 再试（U-Boot 无 2.5G PHY 驱动，CU 四个口都是内建 1G PHY，理论上都行）。
5. 刷完点 `Boot system`；把 PC 网卡改回 `192.168.1.106/24`（网关 `192.168.1.1`）。

---

## 4. 刷完看什么（前 2 分钟就能定性）

| 观察项 | 说明 |
|---|---|
| lan1–lan4 网口灯 | 只要有一口亮，说明 eth 起来了 |
| PC 能否 `ping 192.168.1.1` | QWRT 首启 LAN 固定 `192.168.1.1`（`bin/config_generate` 默认），与 PC 同网段 |
| 手机搜 WiFi | QWRT 首次启动会开 **开放** SSID（`OpenWrt-2.4G` / `OpenWrt-5G` 一类），能搜到 = 内核与 rootfs 都起来了 |
| `Test-NetConnection 192.168.1.1 -Port 22` | QWRT telnet(23) 与 dropbear 默认开，`root`/`password` |

**别用串口也能定性**：灯 / ping / WiFi 三者只要有一样通，就不是内核问题。

---

## 5. 登录后核对（SSH `root` / `password`，或 telnet）

```sh
cat /tmp/sysinfo/board_name          # 期望：fiberhome,hg5585f-cu
cat /proc/device-tree/model          # 期望：FiberHome HG5585F CU
ls /proc/device-tree/ethernet@1fb50000/port@1/   # **不应出现 phy-mode**
cat /proc/device-tree/ethernet@1fb50000/port@1/phy-handle | hexdump -C   # 期望 0000002a
cat /proc/device-tree/mdio@1fb5f01c/ethernet-phy@9/phandle | hexdump -C # 期望 0000002a
ls /proc/device-tree/mdio@1fb5f01c/  # 期望：ethernet-phy@9 @a @b @c，**无 @7**
cat /proc/device-tree/keys/reset/gpios | hexdump -C   # 期望 00000009 00000023 00000001

ip -br link                          # 期望 lan1 lan2 lan3 lan4 + br-lan + pon0
for i in 1 2 3 4; do echo "== lan$i"; ethtool lan$i 2>/dev/null | head -3; done
dmesg | grep -iE 'an7581|phylink|eth[0-9]|phy' | tail -40
uci show network | grep -E 'lan|wan' | head -20
```

判定标准：

- `board_name` = `fiberhome,hg5585f-cu`；`br-lan` 拿到 `192.168.1.1`；
- 插着网线的 **lan2** 有 carrier（`ethtool lan2` 显示 `Link detected: yes`）；
- `dmesg` 里没有 `an7581-bsp-eth` 探测失败的记录（不应出现 `probe failed` / `-22`）。

---

## 6. 判定树

| 现象 | 结论 | 下一步 |
|---|---|---|
| 4 口全通 | **成功** | 进 §7 配置收尾 |
| lan2/3/4 通、lan1 不通 | 部分成功（最低可接受） | 先当 3 口路由用；lan1 单独攻（BSP 可能把 `port@1` 固定映射到 2.5G GDM 通路，需要新增端口节点/`airoha,switch-port` 属性，另开一轮） |
| 完全 ping 不通，但 reset-held 能进 `192.168.0.1` | DTB 改动仍致命 或 该栈不适配 | 刷 **control 包**：能启动→问题锁定在 `port@1/phy@7`；仍不能启动→**QWRT 5.4 BSP 栈跑不了 CU**，转 §8 结论 |
| 完全不通且 reset-held 进不去 | 需要串口 | 插 USB-TTL（3.3V，115200 8N1）抓 log |

---

## 7. 成功后收尾（建议单独一轮做）

1. **保持 LAN `192.168.1.1`**（PC 以太网就在这个网段；不要改成 192.168.31.1，避免与 CT 生产机冲突）。
2. 改 root 密码；给 WiFi 加 WPA2 密码（QWRT 首启是开放的）。
3. PON：`pon.line0.mode='epon-10g-1g'`、`pon.line0_oam.operator='ctc'`、LOID、`ge_ports=4`；WAN `pon0.995` PPPoE。
4. 装回常用插件；`13_opkg_update` 会把 feeds 改成 ImmortalWrt 24.10.6（与 25.12.3 镜像不匹配），**先别 `opkg update`**。

---

## 8. 回滚（任何一步失败都用这个）

1. 断电 → 按住 reset → 上电 → 进 `http://192.168.0.1`（PC 先改 `192.168.0.10/24`）。
2. `Install system` → 选 `ponwrt-airoha-an7581-fiberhome_hg5585f-cu-squashfs-sysupgrade.itb`。
3. 刷完 `Boot system`，PC 改回 `192.168.1.106/24`。
4. 若只想回 QWRT CT 版行为：刷 control 包（lan1 会失效，lan2-4 可用）。

---

## 9. 本包已核验项（`verify_qwrt_cu_v2.py`，30 项全 PASS）

- FIT：`kernel-1` / `fdt-1` / `rootfs-1` 的 `crc32` + `sha1` 全部重算一致；
- `fdt-1` 的 `data-position` = `0x460000`、`data-size` = `14698` 未变；
- DTB `totalsize` = `14698` = `data-size`，`off_dt_struct` / `off_dt_strings` / `size_dt_struct` / `size_dt_strings` 与 CT 原版**逐字节相同**；
- DTB 严格结构校验通过（112 节点 / 41 phandle / 10 条引用全部可解析 / FDT_END 收尾）；
- **与 CT 原版 DTB 的差分恰好 7 项**，多一项即 FAIL；
- `port@1` 无 `phy-mode`，`phy-handle` → `/mdio@1fb5f01c/ethernet-phy@9`（phandle 42）；
- `ethernet-phy@7` 已删除；`keys/reset` gpio = `<9 35 1>`；
- metadata JSON 282 字节不变，`supported_devices` / `board` 均为 cu；
- fwtool 两层 footer CRC（先内层 type=1、再外层 type=0）全部重算一致，`size` 字段仍为 307 / 372；
- **`fdt_check_full()` 通过**（U-Boot 网页刷机同款校验，`net/lwip/httpd.c: validate_firmware_fit`）：
  DTB 的 FDT_NOP 填充必须位于**根节点 END_NODE 之前**，因为在 `fdt_check_full()` 里
  `expect_end && tag != FDT_END → -FDT_ERR_BADLAYOUT`；NOP 若放在根 END_NODE 之后，
  U-Boot 会直接报 `Firmware device tree is invalid.` 并拒绝写盘（已踩过）；
- compatible = `fiberhome,hg5585f-cu` 与 U-Boot 自身板型 DTS
  （`dts/upstream/src/arm64/airoha/an7581-fiberhome-hg5585f-cu.dts`）一致，
  可过 `of_machine_is_compatible()`（否则报 `Firmware target ... does not match this board.`）。

复跑：

```powershell
cd "D:\AI\路由\QWRT-分析"
python verify_qwrt_cu_v2.py "QWRT-R26.10.21-hg5585f-cu-v2.itb" --expect cu `
  --baseline "..\光猫-HG5585F\QWRT-R26.10.21-airoha-an7581-fiberhome_hg5585f-ct-squashfs-sysupgrade.itb"
```

---

## 10. 为什么改这几处（一页解释）

1. **CU 没有外置 2.5G PHY（GPY211C）**：CT 的 lan1 = `gdm4` MAC + 外置 GPY211C（mdio 7、2500base-x）。CU 的 lan1 = **内建 switch port 1 + 内建 PHY1**（mdio 9）。ponwrt 的 CT/CU dtsi 差分与 CU 机 ponwrt 实测都印证。
2. **QWRT 5.4 BSP 内核的 `phy_modes[]` 里没有 `"internal"`**：我在 `kernel-1.gz` 里穷举确认（只有 gmii/sgmii/tbi/rev-mii/rmii/rgmii*/rtbi/smii/xgmii/moca/qsgmii/trgmii/1000base-x/rxaui/xaui/10gbase-kr/usxgmii/5gbase-r）。该内核用 phylink，`of_get_phy_mode()` 对未知串返回错误 → 整块 `ethernet@1fb50000` 不 probe → lan1–lan4 全灭。**所以 `port@1` 的 `phy-mode` 必须整条删除**，与同 DTB 里本来就能用的 `port@2/3/4` 完全同构（它们都没有 `phy-mode`）。
3. **`ethernet-phy@7` 必须删**：CU 没有这颗芯片，留着会让 mdio 去探一个不存在的地址并拨 GPIO34。
4. **reset 键是 GPIO35**：CT DTB 里写成 GPIO0（实为 `uart1_txd`），CU/CT 教科书都是 GPIO35，与 U-Boot 一致。
5. **metadata 必须换 cu**：否则 `fwtool_check_image` 直接拒刷（用户看到的"刷入失败"就是这个）。
