# 01 · 光猫 烽火 HG5585F（现网主路由）

**这一台同时是光猫和主路由**：已刷 ponwrt（QWRT），PON 直接 PPPoE，没有额外路由器。

## 型号与身份
- 烽火 HG5585F，10G-EPON 非对称（`epon-10g-1g`），OAM **CTC** + LOID
- 两个硬件版本各自独立备份：**CU（联通现网在用）** 与 **CT（电信版）**
- 身份数据（LOID / MAC / 分区表 / 刷机记录）见 `身份数据/`

## ⚠️ 最重要的东西
`原厂备份-CU/` 与 `原厂备份-CT/` 是刷机**之前**抓的 NAND 全分区镜像（mtd0–mtd16）。
- **刷机后不可再生**，救砖只能靠它
- `原厂备份-CT/手动备份/` 只保留与 `原厂-20261021/` 不重复的 4 个分区（其余为重复件，已删）
- 校验清单见各自 `校验/` 子目录（sha256）

## 目录
| 子目录 | 内容 |
|---|---|
| `刷机流程/` | 00-开始这里 → 01-刷机流程 → … → 08-QWRT刷机流程；`flash-SOP.md`；`串口日志/`（U-Boot xmodem 抓包） |
| `原厂备份-CU/` `原厂备份-CT/` | NAND 分区镜像 + 校验 + factory-1m.bin + uboot-recovery 页面 |
| `固件/` | ponwrt-v2026.10.18 全套（CU/CT 的 sysupgrade + initramfs recovery，带 sha256sums）、原厂后台一键刷入包 v260921、CT 物料、原厂刷机工具 |
| `身份数据/` | LOID / MAC / 分区表 / WAN 连接 / identity.json |
| `工具/` | `光猫通道开关.bat`、xmodem 发送脚本、fhtool/ont 系列、串口抓包 |
| `分析-CT/` | CT 版 rootfs 取证、PON debug bundle（含 `npu/` 里 PPE 状态、`line-line0/` 里 PON 链路信息） |

## 救砖主线（记住这个就够）
1. 串口（杜邦线）→ 中断 U-Boot → `xmodem` 发 `an7581-fiberhome-hg5585f-{ct,cu}-bl31-u-boot.fip`
2. 进 U-Boot 后走 `uboot-recovery.html`（TFTP）→ 刷 recovery itb
3. 起得来再 sysupgrade 刷正式固件
细节见 `刷机流程/05-风险与救砖.md`。
