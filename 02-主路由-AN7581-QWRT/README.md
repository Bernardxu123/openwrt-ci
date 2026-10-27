# 02 · 主路由固件（Airoha AN7581 / QWRT）

现网主路由就是光猫本体（见 `01-光猫-HG5585F/`），这里放的是**固件层面的东西**：镜像、改造脚本、硬件审计报告、配置备份。

## 现网版本
- **QWRT R26.10.25**（底层 OpenWrt 25.12.3），内核 `5.4.302`，aarch64
- SoC **AN7581**，4×A53，400MB RAM，无 swap

## 目录
| 子目录 | 内容 |
|---|---|
| `固件与镜像/` | `QWRT-R26.10.21-hg5585f-cu-v2.itb`（CU 改造版，当前基线）、`QWRT-R26.10.21-…-ct-squashfs-sysupgrade.itb`（CT 版）、dtb/fit 元数据、`uboot-cu.bin` |
| `分析报告/` | `性能硬件加速PON审计-20261022.md`（PPE/offload 结论）、`每核采样与IRQ归因报告-20261020.md`、`现网优化核查与落地-20261020.md`、`CU改造说明.md`、dtb dump、fit tree |
| `脚本/` | `patch_qwrt_cu*.py`（改 CU 版镜像）、`verify_qwrt_cu_v2.py`、probe 脚本 |
| `备份/` | `round3-baseline/final`（2026-10-24 优化前后快照）、`qwrt-ct-20261022`、`attic-20261016`（daed 时代一次性脚本） |

## 关键结论（详细见 AGENTS.md §3、§7）
- **硬件流量卸载必须关**：`flow_offloading_hw=1` 时 flowtable 设备选成物理口 `pon0`，与 `pppoe-wan` 对不上，下行被压到 ~640Mbps
- 正确配置：`flow_offloading=1` + `flow_offloading_hw=0` → 单站点 914Mbps / 多源 984Mbps，CPU 仅 29%
- 本机 PON 光路干净（CRC/FEC/未纠正码字全 0），MSS clamp 1452 正常
