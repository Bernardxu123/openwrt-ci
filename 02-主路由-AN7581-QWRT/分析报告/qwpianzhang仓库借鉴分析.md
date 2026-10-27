# `qwpianzhang/Actions-OpenWrt-HG5585F` 借鉴分析

> **分析对象**：GitHub `qwpianzhang/Actions-OpenWrt-HG5585F`（分支 `main`，PonWrt 云编译 CI 仓库）
> **移植目标**：`Bernardxu123/ponwrt-hg5585f`（同板型 烽火 HG5585F **CU**，AN7581）
> **目标机现状**：PonWrt / mainline **6.18** / **apk** 包管理 / 438 MB 可用 RAM
> **已有优化**：`flow_offloading_hw=1`（PPE，`npu_attached=1`）、`packet_steering=2`、`netdev_max_backlog=16384`、irq-affinity、wifi-napi-affinity、简版 `/sbin/tempinfo`
> **实测基线**：有线 8 路并发 670 Mbps 时四核合计 busy 仅 **4%**（PPE 卸载已生效）
> **当前 NPU 固件**：`NPU fw version: 1456.62`
> **报告日期**：2026-10-21
> **约束**：本报告只读分析，未修改目标仓库任何文件，未执行任何 ssh/网络写操作。

---

## 0. 一句话结论

**这个仓库里唯一有实质技术含量、且真正独立于「云编译流水线」的东西，是 NPU clanker 固件那条线（4 个脚本 + 2 个包模板）；但它解决的问题不是「多卸载几种流量」，而是「换掉一颗有内存踩踏 bug 的厂商固件」——对一台已经跑通 PPE 有线卸载的机器，收益是「稳定性」而不是「性能」。而它配套的 WiFi 卸载改造要吃掉 110 MiB / 438 MB ≈ 25% 内存，不建议。**

其余部分（tempinfo、diy 脚本、96-wifi-5g-cn、feeds）**没有任何性能调优内容**——diy-part1.sh / diy-part2.sh 里 **一行 sysctl、一行 firewall、一行 RPS/XPS/irqbalance 都没有**。你已经做的 `packet_steering` / `backlog` / irq-affinity 比这个仓库走得更前面。

**完整读完全部 12 个指定文件 + 4 个关联文件后的裁决：**

| 项目 | 裁决 |
|---|---|
| **NPU clanker 固件** | 🟡 **值得做，但只做「换 bin」那一半**；WiFi 卸载那一半明确不做 |
| **tempinfo 完整版** | 🟢 **值得抄**，真正的价值是 `ponctl status --json` + `jsonfilter` 取光模块数据的写法 |
| **diy-part1/2.sh** | ⚪ **无性能价值**，仅「包索引进 `package/custom` 不用注册 feed」这条方法论有用 |
| **96-wifi-5g-cn** | 🔴 **不要抄**，HE160 默认值对你这台机器是**倒退**（你已明确选 80MHz） |
| **feeds.conf.default** | 🔴 **解决不了 apk 404**，它压根不含任何运行时包源 |
| *（额外发现）* **`luci-app-airoha-npu`** | 🟢 **本仓库性价比最高的可落地项**，但它在 `diy-part1.sh` 的插件清单里，不在你给的 12 个文件内 |

---

## 0.1 事实核对表（先说清楚哪些是查证的、哪些是推断的）

| 结论 | 证据等级 | 依据 |
|---|---|---|
| 12 个指定文件全部 200，无需回落 master | ✅ 直接查证 | 全部 web_fetch 成功 |
| ponwrt 自有 `feeds.conf.default` 与该仓库**完全相同**，后者只多一行 `nikki` | ✅ 直接查证 | 两文件逐行比对 |
| `an7581-npu-wlan.dtsi` **已存在于 ponwrt master**，只差板级 DTS 去 include | ✅ 直接查证 | 拉取 ponwrt 该文件 + hg5585f common dtsi |
| stock 固件包是 **`EN7581+MT7992`**（eagle 数据面） | ✅ 直接查证 | ponwrt `package/firmware/linux-firmware/airoha.mk` 的 TITLE 字符串 |
| HG5585F（CT/CU）无线是 **MT7916D（kite）** | ✅ 直接查证 | `an7581-fiberhome-hg5585f-common.dtsi` 的 `wifi@0,0` + configs 注释 |
| 4 个保留内存区合计 **110.0 MiB** | ✅ 直接查证 | 0x2C00000(44M)+0x4000000(64M)+0x6800(26K)+0x200000(2M) |
| `apply-npu-dts.sh` **只**在 `npu_fw=clanker` 时被调用 | ✅ 直接查证 | workflow `Build NPU firmware package` 步骤内 |
| ClankerNPU 的 `Verified paths` **只列了 AN7583 + MT7993** | ✅ 直接查证 | ClankerNPU `docs/errata.md` 末节 |
| **目标仓库就是完整 ponwrt 源码树，`files/` 是真正的 rootfs overlay**（决定落地方式，见 §0.2） | ✅ 直接查证 | 本地 `D:\AI\路由\firmware\ponwrt-hg5585f`：有 `Makefile`/`target/`/`toolchain/`/`scripts/kconfig.pl`，CI 用 `gen-config.sh` 分层生成 `.config` |
| **目标仓库的 `tempinfo` 已经用了 `ponctl --json` + `jsonfilter`** | ✅ 直接查证 | 读 `files/sbin/tempinfo`（37 行）：已取 `@.frontend.temperature_celsius` |
| **目标仓库已有 `scripts/hg5585f/`，有 `build.yml` 和 `keep-cache-alive.yml`** | ✅ 直接查证 | 目录列举；对照分析：qwpianzhang 的 CI 设计**已被它借鉴** |
| 目标仓库 `target/linux/airoha/dts/` 里 **`an7581-npu-wlan.dtsi` 在位**，且已有 `an7581-npu-mt7992.dtsi` / `an7581-npu-mt7996.dtsi` 两个现成 include 包装 | ✅ 直接查证 | 目录列举 + grep include 链 |
| 目标仓库 `DEFAULT_PACKAGES` 里 **stock NPU 固件仍在**，且 `configs/an7581.config` 有 `CONFIG_PACKAGE_airoha-en7581-npu-firmware=y` + `CONFIG_DEFAULT_/MODULE_DEFAULT_` 三行 | ✅ 直接查证 | `an7581/target.mk` + grep `configs/*.config` |
| HG5585F 板级 DTS **没有** `airoha,npu` 属性、也**没有** include 任何 npu dtsi（只有 evb / valyrian / w1700k 有） | ✅ 直接查证 | grep `npu-wlan\|an7581-npu` 命中 7 个 dts，无 hg5585f |
| 你的 `1456.62` 属于厂商版 / clanker 版 | ⚠️ **推断** | 厂商版号格式典型；clanker 版 boot 行带 git hash。需实机比对确认 |
| E10 bug 在你这台 512 MB 机器上表现为 DRAM 踩踏还是取数异常 | ⚠️ **推断，未实测** | 见 §1.6.2 的地址分析 |
| ponwrt 是否有运行时 apk 仓库文件 | ❌ **未确认** | 猜测路径 404，未穷举 |

---

## 0.2 落地方式修正：目标是完整源码树，不是纯 CI 仓库

我发现 `D:\AI\路由\firmware\ponwrt-hg5585f` 是**完整的 ponwrt fork**（`upstream` 指向 `pbs05/ponwrt`），它已经有：

```
Makefile  target/  toolchain/  tools/  include/  package/  scripts/
files/                       ← 真正的 rootfs overlay（9 个文件）
  ├── etc/uci-defaults/99-hg5585f-setup   (10917B，含 flow_offloading / packet_steering / sysctl)
  ├── etc/init.d/irq-affinity  +  wifi-napi-affinity
  ├── etc/init.d/pon-watchdog  +  usr/sbin/pon-watchdog
  ├── etc/config/{pon,dhcp}
  └── sbin/tempinfo                        (1360B，37 行简版)
configs/                     ← 7 个分层 config（an7581/an7583/release/hg5585f-profile/hg5585f-build/两个 proxy 层）
scripts/hg5585f/             ← gen-config.sh / assert-config.sh / kmerge.py / collect-artifacts.sh
scripts/kconfig.pl           ← 分层合并器
.github/workflows/build.yml  ← 已含 gen-config.sh 分层、ccache、feeds(+pon_drivers/pon_userspace)
```

**这带来三条对结论有实质影响的修正：**

### 修正 1：`strip-default-npu-fw.sh` 对你会直接可用（不需要那套 CI 编排）

因为你有完整 `target/linux/airoha/**`。它的唯一作用是把 stock 固件从 `DEFAULT_PACKAGES` 摘掉。你的现实状态（已核实）：

| 位置 | 现状 |
|---|---|
| `target/linux/airoha/an7581/target.mk` | `DEFAULT_PACKAGES += airoha-en7581-npu-firmware kmod-nf-conntrack-bridge uboot-envtools` ← **仍含 stock** |
| `configs/an7581.config:120` | `CONFIG_DEFAULT_airoha-en7581-npu-firmware=y` |
| `configs/an7581.config:121` | `CONFIG_MODULE_DEFAULT_airoha-en7581-npu-firmware=y` |
| `configs/an7581.config:2985` | `CONFIG_PACKAGE_airoha-en7581-npu-firmware=y` |
| `configs/an7581.config:2984` | `# CONFIG_PACKAGE_airoha-en7581-mt7996-npu-firmware is not set` |

⇒ 若你要换成自己的固件包，**必须同时处理这 5 处**（脚本只覆盖第 1 处，`.config` 里的 2–4 处要在 `configs/hg5585f-build.config` 覆盖层里压掉）。这正是 qwpianzhang 的 `Select NPU firmware package`（7.5 步）在 CI 里干的事——你有 `kmerge.py`，改 `hg5585f-build.config` 更干净。

具体到 `configs/hg5585f-build.config`（它是 kconfig 链**最后一步**，`# ... is not set` 能压掉前面所有层，`gen-config.sh` 注释已确认这个语义）：

```kconfig
# ---- 换掉 stock NPU 固件（MT7992/eagle）----
# 三行都要写：PACKAGE 之外还有 DEFAULT_ / MODULE_DEFAULT_，
# 少写一个 defconfig 就会把 stock 包拉回 rootfs
# CONFIG_PACKAGE_airoha-en7581-npu-firmware is not set
# CONFIG_DEFAULT_airoha-en7581-npu-firmware is not set
# CONFIG_MODULE_DEFAULT_airoha-en7581-npu-firmware is not set
# CONFIG_PACKAGE_airoha-en7581-mt7996-npu-firmware is not set

# ---- 装 clanker 版（包名由 gen-npu-fw-package.sh 生成）----
# CONFIG_PACKAGE_airoha-en7581-mt7916-npu-firmware=y
```
**但注意**：`DEFAULT_PACKAGES`（`target/linux/airoha/an7581/target.mk`）那处**改不动 config**——它会在 `make defconfig` 时按 `CONFIG_TARGET_*` 重新展开。所以要么跑 `strip-default-npu-fw.sh`（改 target 树），要么接受同名文件被覆盖（而 `files/lib/firmware/airoha/` 在 ipk 安装**之后**才铺，**必然覆盖**——这就是 `FALLBACK_FILES=true` 那条路径能生效的原因）。

> **最省事的一条路**：既然文件同名、`files/` 必然覆盖，就直接把两个编好的 bin 放进 `files/lib/firmware/airoha/`。**不用改任何 config、不用 strip、不用建包。**代价是「不可选」（包置 n 也照样生效），但对你「只要换掉这台机器的固件」的目标完全够用。qwpianzhang 之所以搞得那么复杂，是因为它要支持**11 个变体 × 多机型**的可选矩阵——你不需要。

### 修正 2：有比 `luci-app-airoha-npu` 更省事的路径，但两者互补

`target/linux/airoha/dts/` 里**已经有**：
- `an7581-npu-wlan.dtsi`（110 MiB 那 4 块）
- `an7581-npu-mt7992.dtsi` / `an7581-npu-mt7996.dtsi`（各自 `#include "an7581-npu-wlan.dtsi"` + 写 `firmware-name`）

但 **HG5585F 的 DTS 一个都没 include**（只有 `an7581-evb*.dts`、`an7581-nokia-valyrian.dts`、`an7581-w1700k-ubi.dts` 用了）。所以 `apply-npu-dts.sh` 要做的事**已经有现成的 dtsi 可以直接 include**，不必跑脚本生成。**但结论不变：不建议 include**（110 MiB / 25% 内存，且 stock 固件变体是 MT7992 不是 MT7916）。

### 修正 3：`tempinfo` 只需要「加几个字段」，不是重写

你的 `files/sbin/tempinfo` **已经在用** `ponctl --json` + `@.frontend.temperature_celsius` 了。所以 §7.1 的价值**下降为**「补上 `tx_power_dbm` / `rx_power_dbm` / `tx_bias_ma` / `voltage_volts` 四个字段 + `uci get pon.@xpon[0].device` 的设备名探测」。

顺带发现你简版里两个**可以立刻改的小问题**：
1. 硬编码 `--device pon0`（第 26 行），而完整版用 `uci -q get pon.@xpon[0].device` 探测——设备名一旦变化就静默失效
2. WiFi 只扫 `phy*/hwmon*/temp1_input`，**漏了 `phy*/device/hwmon/hwmon*/temp1_input`** 这条路径（mt76 两种挂法都出现过）
3. 输出顺序是 `CPU, PON, WiFi`，LuCI 惯例是 `CPU, WiFi, PON`（纯观感）

---

## 1. NPU clanker 固件详述（重点）

### 1.1 「clanker」是什么

**不是厂商固件的变体，不是增强补丁，而是一份从零重写的裸机固件。**

- 上游：`ClankerConstruction/ClankerNPU`，标题 *"Clankered Airoha AN75XX NPU Firmware"*
- 定性：Airoha AN7552 / AN7581 / AN7583 内置 **RISC-V 网络处理器（NPU）**的 **bare-metal 固件**（RV32IMC 多 hart，无 OS、无 MMU，每个 hart 跑一个轮询循环）
- 「Clanker」= 项目/作者群的名字，不是技术术语。仓库里 `CLANKER=1` 指的是「适配 Clanker 自己改过的 host 驱动」，与固件功能无关
- 规格（AN7581）：**8 harts / 480 KB SRAM**；MT7916、MT7992、MT7996 三种 WiFi 芯片各一个独立镜像
- 数据面分两类：**MT7916 / MT7996 → kite**，**MT7991 / MT7992 / MT7993 → eagle**。两个数据面镜像**不通用**

它干的事（按上游 README 的系统框图）：主机加载镜像后经 mailbox 配置各子系统；WiFi 帧从 WiFi 芯片进入 NPU SRAM 的 ring，NPU 经 TDMA 送有线侧或经 host adaptor 送主机；需要隧道头改写的包走 NPU bridge；PPE / QDMA / GDM 由它编程。

### 1.2 与当前跑的 1456.62 是什么关系：**替换，不是叠加**

这是最关键的一条，直接决定移植方式：

| | 你的现状（stock） | clanker |
|---|---|---|
| 文件名 | `/lib/firmware/airoha/en7581_npu_rv32.bin`<br>`/lib/firmware/airoha/en7581_npu_data.bin` | **完全相同两个名字** |
| 大小上限 | rv32 ≤ 2 MiB，data ≤ 64 KiB | 同 |
| 加载地址 | rv32 → DRAM `0x84000000`；data → NPU SRAM `0x3E900000` | 同 |
| host 驱动 | `drivers/net/ethernet/airoha/airoha_npu.c`，按固定名字 `request_firmware_direct()` | **同一个驱动，不改** |
| mailbox 接口 | — | 同（`CLANKER=0` 时完全对齐 stock 驱动） |

**结论：这是同一个二进制槽位的等价替换。** 仓库为此做了两件「防撞车」的事，正是替换关系的证据：

1. 包模板里写 `conflicts = airoha-en7581-npu-firmware ...`——因为两个包装同一批文件名
2. `strip-default-npu-fw.sh` 把 stock 从 `DEFAULT_PACKAGES` 摘掉——否则 `make defconfig` 会把它拉回 `=y`，两个包同时进 rootfs，**谁生效取决于安装顺序**

> ⚠️ 顺带一个**对你有用的独立发现**：ponwrt 的 stock 包 TITLE 是 `Airoha EN7581+MT7992 NPU firmware`——也就是说**出厂装的固件是为 MT7992（eagle）编的，而 HG5585F 的无线是 MT7916（kite）**。数据面不匹配 ⇒ **在这块板子上，WiFi→NPU 卸载从来就不可能工作**，跟有没有 include 那个 dtsi 无关。这解释了为什么 ponwrt 默认不加 `npu-wlan.dtsi`——加了也是白烧 110 MiB。详见 §1.5。

### 1.3 四个脚本各自干什么

| 脚本 | 干什么 | 需要本地编译吗 | 依赖 |
|---|---|---|---|
| `strip-default-npu-fw.sh` | 从 `target/linux/airoha/**` 的 `DEFAULT_PACKAGES` / `DEVICE_PACKAGES` 里**摘掉**包名匹配 `airoha-[A-Za-z0-9_.-]*npu-firmware` 的 token。用 perl 跟踪**反斜杠续行**状态（否则会漏掉续行里的 token）。摘完复核，有残留打印 `[RESIDUAL]` 并 `exit 3` | 否（纯文本改写） | perl |
| `build-npu-fw.sh` | **下载并现场交叉编译**：① 从 GitHub Releases 拉 `xpack-riscv-none-elf-gcc 14.2.0-3`（约 100 MB，**必须是 elf/newlib 工具链**，`riscv64-linux-gnu` 编不了裸机）② `git clone` ClankerNPU ③ `make CROSS=riscv-none-elf- SOC=… WIFI=…` ④ **体积自检**（超 2 MiB / 64 KiB 直接失败，不产出「刷上才炸」的镜像） | **是** | bash/git/curl/tar/make + 下载的工具链 |
| `gen-npu-fw-package.sh` | 循环调 `build-npu-fw.sh` 编各变体，然后把两个 bin 塞进 `package/custom/airoha-<soc>-<wifi>-npu-firmware/src/`，用 `Makefile.in` 模板生成标准 OpenWrt 包（`CONFIG_PACKAGE_xxx=y` 可勾）。含与 linux-firmware 已占包名的**自动改名**（AN7581+MT7996 → 加 `-clanker` 后缀） | 否（调度器） | — |
| `apply-npu-dts.sh` | ① 生成 `an7581-npu-clanker.dtsi`（内容就是 `#include "an7581-npu-wlan.dtsi"`）② 把它插入板级 DTS 的 `#include "an7581.dtsi"` 之后 ③ 固件名前缀非默认时才写 `&npu { firmware-name = ... }` | 否（纯文本改写） | sed/grep |

### 1.4 `strip-default-npu-fw.sh` 从什么里剥离什么

**剥离对象**：`target/linux/airoha/` 下所有含 `DEFAULT_PACKAGES` / `DEVICE_PACKAGES` 赋值的文件（`an7581/target.mk`、`image/an7581.mk` 等）
**剥离内容**：token `airoha-*-npu-firmware`
**不剥离**：`.config` 里的选中项、`package/firmware/linux-firmware/airoha.mk` 里的**包定义**（脚本注释明说「正常且必须保留，`npu_fw=stock` 还要靠它」）

实机核对，ponwrt `an7581/target.mk` 里确实是：
```make
DEFAULT_PACKAGES += \
	airoha-en7581-npu-firmware kmod-nf-conntrack-bridge uboot-envtools
```
`strip-default-npu-fw.sh` 会把第一个 token 摘掉，保留后两个。脚本注释里还点名「实测 an7581/target.mk 第 9 行、image/an7581.mk 第 163 行」漏过——这条已与真实文件对上。

### 1.5 `apply-npu-dts.sh` 往 DTS 里加什么（以及为什么你不该加）

它加的东西只有一样：`#include "an7581-npu-wlan.dtsi"`。而这个 dtsi **ponwrt master 里已经有了**，内容是：

```dts
/ {
	reserved-memory {
		npu_pkt:      npu-pkt@8a000000      { no-map; reg = <0x0 0x8a000000 0x0 0x2c00000>; };  /* 44 MiB */
		npu_txpkt:    npu-txpkt@8cc00000    { no-map; reg = <0x0 0x8cc00000 0x0 0x4000000>; };  /* 64 MiB */
		npu_txbufid:  npu-txbufid@90c00000  { no-map; reg = <0x0 0x90c00000 0x0 0x6800>;    };  /* 26 KiB */
		npu_ba:       npu-ba@90c06800       { no-map; reg = <0x0 0x90c06800 0x0 0x200000>;  };  /*  2 MiB */
	};
};

&npu {
	memory-region = <&npu_binary>, <&npu_pkt>, <&npu_txpkt>, <&npu_txbufid>, <&npu_ba>;
	memory-region-names = "binary", "pkt", "tx-pkt", "tx-bufid", "ba";
};
```

**合计 = 44 + 64 + 2 MiB + 26 KiB = 110.03 MiB。**

这个 dtsi 自己的文件头注释就是最好的说明（ponwrt 原文）：

> *"Memory regions used by the NPU Wi-Fi packet offloading only. Boards that do not run an Airoha-offloaded Wi-Fi chip **must not reserve them**: the NPU needs the binary region alone to run its firmware and to offload flows."*

翻译成你的场景：

- **有线 PPE / HWNAT 卸载（你现在这套）只需要 `npu_binary`，完全不需要这 4 块**
- 这 4 块是 **WiFi 卸载专用**（`airoha_npu_wlan_init_memory()` 按名字查 `pkt` / `tx-pkt` / `tx-bufid` / `ba`，缺一个 WiFi 卸载初始化就失败）
- 代价 **110 MiB / 438 MB ≈ 25% RAM**

### 1.6 有没有实质收益？（这是你问的核心）

#### 1.6.1 「能不能多卸载一些流量类型」——**有线侧：不能**

clanker 固件与 stock 固件走的是**同一套 PPE / FOE 流表**：

- FOE 表 AN7581 的硬件上限是 **16384 项**——跨两个 PPE 的 SRAM：表配置 `0x1FB50E1C` 的 bits 26:24 给大小（`1024 << n`），`0x2000` 起的表项属于第二个 PPE。**但实际能拿到多少取决于 NPU init 时有没有把第二个 PPE 也启用**：上游原文是「With the second PPE already enabled at init, both PPEs get 8192 each」——单 PPE 则 8192。这一条对你的意义仅是「表项上限」这种理论数字，不影响你 328 条的现状（见 §10 第 7 条）
- 支持的卸载类型完全一样：IPv4/IPv6 路由转发、VLAN、PPPoE（含 VLAN 后的 PPPoE 长度补丁）、**VXLAN 硬件封装/解封装（UDF 1..40）**、**SRv6（UDF 41..56）**、**地址映射 MAP-T（UDF 65..68）**、**L4S ECN 标记**
- 上游 errata 的 `Verified paths` 明确写：*"this firmware and the vendor firmware give the same results for routing, VXLAN, SRv6, L4S"*——**等价，不是增强**

所以：**不会有「新的可卸载流量类型」**。你已有的 328 条 PPE 表项那一套不会因为换固件而变多。VXLAN/SRv6/MAP-T 的卸载能力 stock 固件同样有（前提是 host 侧真的绑了这种 flow）。

#### 1.6.2 真正拿到的是 **errata 修复**（这才是价值所在）

上游 `docs/errata.md` 列了 E1–E10 + H1–H5。**筛掉只影响 WiFi 的**，对「有线 + mainline mt76 无线」这台机器相关的只剩 3 条：

| id | 缺陷 | 与你的相关性 |
|---|---|---|
| **E10** | 核 3 的 package check 要给"包里没有的端口"下电；`mtk_usb_powerdown` 把 store 的两个操作数搞反了——**把 PHY 寄存器地址（`0x1FAC080C` / `0x1FAE080C`）写到了**由新 PHY 值拼出来的地址 `(value & 0x5FFFFFFF) \| 0xA0000000` 上，**那是 host DRAM**。后果：PHY 没下电，且**一个 host 内存字被覆盖**，或者在没映射 DRAM 的地方触发 store 异常。上游明说「能力表里每个缺端口的能力都缺 USB port 2，**每个缩减版 package 都会命中**」 | 🔴 **最值得关注**。HG5585F DTS 同时开了 usb0 + usb1，port 2 缺失 ⇒ 命中条件成立。clanker 的修法是「把新值写到 PHY 寄存器」 |
| **E1** | tunnel mail 分发用 host 给的功能号索引一个 10 项的函数表，**不检查边界**；id ≥ 10 会调用表后面的任意字 | 🟡 理论上是任意执行，实际取决于 host 驱动会不会发越界 id。你的 `npu_attached=1` 说明 tunnel 子系统是活的 |
| **E7** | 异常处理里打印日志；若同一 hart 正持着 print 互斥又恰好异常，**hart 直接冻死**，且什么都没留下 | 🟡 诊断价值。clanker 改为先把 `mcause/mepc/mtval/ra/sp` 写进 debug block 再打印 |

明确**保留未修**的（`Kept`）：E4（bridge channel 3 无人轮询）、E5（AN7583 DBA 4 项 ONU 表越界）、E6（L4S 计数合并 + 打印文字错）、E8（boot 时重复注册 ISR 打一行 Error）。E2/E3/E9 全是 WiFi。

**E10 在你这台 512 MB 机器上到底怎么表现——这里必须诚实标注为推断：**

`an7581-fiberhome-hg5585f-common.dtsi` 的内存节点是 `reg = <0x0 0x80000000 0x0 0x20000000>`，即 DRAM 覆盖 `0x80000000`–`0xA0000000`。E10 的写入目标 `(value & 0x5FFFFFFF) | 0xA0000000` **恰好是 DRAM 末端之外一个字节起**：
- 若 `value` 很小（PHY 值通常是低位宽），目标 ≈ `0xA0000000`–`0xA0000FFF` 一带 ⇒ **落在 DRAM 之外，store 触发异常**
- 若 `value` 高位有值，`& 0x5FFFFFFF` 可能把地址压回 DRAM 内部 ⇒ **真的踩一个 host 内存字**

两种情况都不会打印、不会崩内核，属于「静默」类缺陷。**建议实测确认，但不必恐慌**（你的机器已经跑了很久没见异常）。核查方法见 §9 第 3 步。

#### 1.6.3 WiFi 流量能不能也卸载？——**能，但代价 110 MiB，且必须先解决镜像变体不匹配**

想启用 WiFi→NPU 卸载，需要**三个条件同时满足**，缺一不可：

1. **换成数据面对得上的固件**：`SOC=AN7581 WIFI=MT7916`（kite）。你现在装的 stock 是 MT7992（eagle），**数据面不匹配，WiFi 卸载根本起不来**
2. **board DTS include `an7581-npu-wlan.dtsi`**（即 `apply-npu-dts.sh` 干的事）
3. **接受 110 MiB 内存被 `no-map` 吃掉**

付 110 MiB（25% RAM）能换来什么：WiFi rx 帧不进 ARM —— NPU 做 BA 重排、TDMA 送 PPE、PPE 转发，未转发的走 BME ring 回 host。理论上「WiFi ↔ 有线」这段转发可以完全脱离 CPU。

**但这台机器的现实是**：现有 WiFi 流量（`bernard_5G` ch149 HE80）并发压力不大，而有线侧 670 Mbps 时四核 busy 只有 4%。**为了让一段本来就不忙的 WiFi 转发再省一点 CPU，付出 25% 内存——性价比明确为负。**

> 上游自己也给了出口：`npu_wlan_mem=false` ⇒「只想要有线 PPE / HWNAT 卸载」。这正是你该选的。

### 1.7 裁决：值不值得移植

| 子项 | 收益 | 可移植性 | 风险 | 工作量 |
|---|---|---|---|---|
| **只换固件 bin（不碰 DTS）** | 3/5 修 E10/E1/E7，稳定性提升；`npu_attached=1` 的路径不变 | 4/5 文件名/加载地址/mailbox 全一致，`CLANKER=0` 即对齐 stock 驱动 | 3/5 **不是厂商代码**；`Verified paths` 只验证过 AN7583+MT7993，**AN7581 未列入**；`npu_src_ref=main` 会漂 | 2/5 需一次交叉编译环境，但不用改 DTS/驱动 |
| **WiFi 卸载（dtsi + kite 变体）** | 2/5 仅 WiFi 转发省 CPU | 3/5 ponwrt 已带 dtsi，`airoha,npu` 属性已在板级 dts 里 | 5/5 **吃 110 MiB / 438MB**，且需先解决变体不匹配 | 4/5 换固件 + 改 DTS + 重新验证 WiFi 稳定性 |
| **`strip-default-npu-fw.sh` 方法论** | 2/5 只在你真要换固件时有用 | 5/5 纯文本脚本，直接可用 | 1/5 只改 target 元数据 | 1/5 复制即用 |

**结论：值得做「只换 bin」那一半，明确不做 WiFi 卸载那一半。**
但有两个前置条件必须先满足：
1. **能编译**——需要一次性 x86-64 Linux 环境（WSL 也行）+ 能访问 GitHub Releases（下载 100 MB 工具链）
2. **能回滚**——两个 bin 备份好，`dmesg | grep -i npu` 记下当前 `1456.62`，改完对比

---

## 2. `files/sbin/tempinfo` 完整版 vs 我们的简版

### 2.1 它是什么

一个 4.4 KB 的 POSIX sh 脚本，**不是 LuCI 插件**。调用链（脚本头部注释写得很清楚）：

```
luci-mod-status/.../include/10_system.js
  → callTempInfo() → rpcd 方法 luci.getTempInfo → 执行 /sbin/tempinfo
  → 输出非空则在「系统」表格插入「温度」行
```

**存在理由**（这条是真正有用的信息）：`autocore` 的 Makefile 只在 `ipq%` / `mediatek%` / `qualcommax%` 这几个 TARGETID 下装 `files/tempinfo`，**`airoha`（AN7581/AN7583）不在列表内**，所以 ponwrt 原生固件**没有** `/sbin/tempinfo`，概览页没有温度行。它靠 `files/` 覆盖进 rootfs 补这个洞。

**授权也不需要额外 ACL**：`autocore` 装的 `/usr/share/rpcd/acl.d/luci-mod-status-autocore.json` 无条件授权 `luci.getCPUInfo` / `luci.getTempInfo`。

### 2.2 逐项回答你的四个问题

| 你问的 | 答案 |
|---|---|
| 有没有多传感器（DDR/PHY/光模块多路）？ | **没有 DDR、没有 PHY 温度**。只有三类：CPU（`thermal_zone0`）、WiFi（遍历 `ieee80211/phy*/hwmon*/temp1_input` **和** `phy*/device/hwmon/hwmon*/temp1_input` 两种路径）、PON 光模块（`ponctl`）。WiFi 是多 phy 拼接（`46.0°C 48.0°C`） |
| 有没有给 LuCI 用的 JSON 输出模式？ | **没有**。输出就是**一行人类可读文本**，LuCI 直接塞进表格。唯一的 JSON 是它**读** `ponctl` 的输出，不是它**产**的 |
| 有没有风扇控制？ | **没有**。纯读 |
| 有没有阈值告警？ | **没有**。无比较、无 exit code、无 logger |

### 2.3 真正的增量（相对我们的简版）

1. **用 `ponctl` 而不是直接读 sysfs**——这是最大收获：
   ```sh
   pon_dev="$(uci -q get pon.@xpon[0].device)"
   ponctl --device "$pon_dev" status --json
   ```
   `ponctl`（`airoha-ponctl`，Rust 二进制）已经在 `status.rs` 的 `convert_optics()` 里做完了 SFF-8472 换算：
   | 原始字段 | 换算 | 输出 |
   |---|---|---|
   | `temperature_8472` | ÷ 256 | `temperature_celsius` (°C) |
   | `tx_power_8472` / `rx_power_8472` | 10log10 − 40 | `tx_power_dbm` / `rx_power_dbm` (dBm) |
   | `tx_bias_8472` | × 0.002 | `tx_bias_ma` (mA) |
   | `voltage_8472` | × 0.0001 | `voltage_volts` (V) |

   然后 `jsonfilter -q -e '@.frontend.temperature_celsius'` 取值。**这比自己解析 `/sys/.../hwmon` 或 i2c 原始字节可靠得多。**

2. **`SHOW_PON_OPTICS=0/1` 开关**：`1` 时温度行顺带发光功率/收光/偏置/电压，一行显示全套；`0` 只给温度。
   仓库**默认 0**——因为它同时启用了 `luci-app-pon-status` 卡片（表格形式展示同一组数据），避免重复。
   脚本注释还给了一个很好的开销提醒：*「概览页轮询 3 秒，`tempinfo` 每 3 秒跑一次 `ponctl`；`luci-app-pon-status` 卡片也每 3 秒调一次 ⇒ 叠加约每 1.5 秒一次 `ponctl`」*。

3. **健壮性细节**：每层都有 `-r`/`-x` 守卫；`fmt_c()` 用 awk 做 `×1000 → %.1f°C`；最后 `printf '%s'`（**不换行**，且兜底 `No temperature info`）。

### 2.4 裁决

| 收益 | 可移植性 | 风险 | 工作量 |
|---|---|---|---|
| 3/5 概览页温度行 + 光模块一览，纯可观测性，无性能收益 | **5/5** 纯 sh，依赖 `ponctl` + `jsonfilter`（你都有：`airoha-ponctl=y`、`jsonfilter=y`） | 1/5 只读 | 1/5 直接覆盖 `/sbin/tempinfo` |

**建议：抄「`ponctl --json` + `jsonfilter`」这一段**，就地升级你现有的简版；`SHOW_PON_OPTICS` 设 `1`（你没有 pon-status 卡片，不会重复）。

---

## 3. `diy-part1.sh` / `diy-part2.sh`：里面有什么我们可能没有的配置？

### 3.1 先说负面结论（重要，避免你去找不存在的东西）

我逐行读完了两个脚本。**它们完全没有**：

- ❌ 任何 `sysctl`（无 `netdev_max_backlog`、无 rmem/wmem、无 tcp 拥塞控制）
- ❌ 任何 firewall 设置（无 `flow_offloading*`、无 fullcone、无 nft 规则）
- ❌ 任何 DNS 设置（无 dnsmasq 参数、无 DoH/DoT）
- ❌ 任何 **`uci set`** —— 除了「5G WiFi 参数」和「时区」这两组（都在 uci-defaults 里，见 §4）
- ❌ 任何 `CONFIG_NET_AIROHA*` / `CONFIG_NPU*` / `CONFIG_PPE*` / `CONFIG_FLOW_*` / hwnat
- ❌ 任何 **RPS / XPS / irqbalance / smp_affinity**
- ❌ 任何无线性能参数（无 `noscan`、无 `beacon_int`、无 `txpower`、无 `amsdu`）

**`diy-part1.sh` 只做一件事**：`git clone` 插件到 `package/custom/`。**`diy-part2.sh` 只做三件事**：时区、5G WiFi 默认值、固件版本号后缀。

**你已有的 irq-affinity / packet_steering=2 / backlog=16384 这三项，这个仓库一项都没有。你在这条线上领先。**

### 3.2 唯一有方法论价值的一条（值得记住）

`diy-part1.sh` 里有一段很长、很硬的注释，讲**怎么让本地包进入 buildroot 索引**。这是真实踩坑记录，对任何要往 ponwrt 加包的人都适用：

> **判据是 `tmp/.packageinfo`，不是 `package/feeds/custom`**
> `prepare-tmpinfo` 直接扫 `package/` 目录树（`include/scan.mk`: `find -L package -mindepth 1 -maxdepth 5 -name Makefile`），`package/custom/<pkg>/Makefile` 深度只有 3，本来就会被扫到，**根本不需要注册 feed**。
> 以前那套 `src-link custom feed` 有两个问题：① `feeds/custom` 指向 `package/custom`，而 `feeds/base` 已指向 `../package`，同一批 Makefile 被扫两遍，`package-metadata.pl` 按 `Override` 挑一个，**行为随扫描顺序漂移**；② `scripts/feeds` 的 `install_src()` 里 `$installed{$name}` 已非空，直接 `return 0`，压根不建 `package/feeds/custom/<pkg>` 符号链接 ⇒ **「`package/feeds/custom` 不存在」是正常现象**，拿它当判据必然误报。

配套的两个坑（都是真的会让人调半天的那种）：
```sh
# 强制重建索引：只删 .packageinfo 不够 —— prepare-tmpinfo 有 scan_unchanged
# 优化（拿 tmp/info/.scan-*.stamp 比 mtime），stamp 还在就会跳过扫描，
# 于是 .packageinfo 被删了却没人重建，索引反而空了。
rm -f tmp/.packageinfo tmp/.targetinfo
rm -f tmp/info/.scan-packageinfo.stamp tmp/info/.scan-targetinfo.stamp
rm -f tmp/.config-package.in tmp/.config-target.in
make -s prepare-tmpinfo OPENWRT_BUILD=
```
```sh
# 包目录名必须等于包名（buildroot 约定 PKG_NAME ?= $(notdir ${CURDIR})），
# 否则 .config 里的 CONFIG_PACKAGE_xxx 符号对不上
```

还有一条 **luci.mk 的 i18n 陷阱**（这个很隐蔽，值得抄走）：
> `luci.mk` 的 i18n 规则是 `po2lmo $(po) → i18n/$(basename $(notdir $(po))).$(lang).lmo`，即 **lmo 名取自 po 文件主名**；而运行时按 `LUCI_BASENAME = $(patsubst luci-app-%,%,luci-app-xxx)` 查找。上游 po 文件叫 `luci-app-airoha-npu.po`，生成 `luci-app-airoha-npu.zh-cn.lmo`，**前端按 `airoha-npu` 找 → 中文不生效**。修法：把 po 改名成 `<basename>.po`。

### 3.3 `.config`（`configs/fiberhome_hg5585f-cu.config`）里值得对照的项

注意：这**不是** diy 脚本的内容，是同仓库 `configs/` 下的机型 diffconfig（约 440 行）。挑与你相关的：

| 项 | 值 | 对你的意义 |
|---|---|---|
| `CONFIG_USE_APK=y` `CONFIG_SIGNED_PACKAGES=y` `CONFIG_SIGNATURE_CHECK=y` `CONFIG_SIGN_EACH_PACKAGE=y` `CONFIG_SIGN_FIRMWARE=y` | 全开 | **apk + 全量签名**——这就是你「opkg 源 404」的根因所在的同一代切换。他们也是 apk，但**不依赖运行时源**，全部编译进固件 |
| `CONFIG_PACKAGE_kmod-nf-flow=y` `kmod-nft-offload=y` `kmod-nf-conntrack-bridge=y` | =y | PPE 卸载的三个前置（你已有，否则 `flow_offloading_hw` 不会生效） |
| `CONFIG_PACKAGE_kmod-nft-fullcone=y` + `luci-app-natmode` | =y | 全锥形 NAT1 / 受限 NAT3 / 对称 NAT4 三选一 |
| `CONFIG_PACKAGE_kmod-tcp-bbr=y` | =y | BBR 可用（但你 PC 侧用不上，路由器自身出站才用） |
| `CONFIG_PKG_FORTIFY_SOURCE_1` / `RELRO_FULL` / `SSTRIP` / `MOLD` / `KERNEL_CC_OPTIMIZE_FOR_PERFORMANCE` | 全开 | **体积/安全取向**：fortify **1**（不是 2/3）、sstrip 剥符号、mold 链接。对性能几乎无影响，对镜像体积有帮助 |
| `CONFIG_KERNEL_DEBUG_INFO=y` + `DEBUG_INFO_REDUCED=y`，**无 `DEBUG_INFO_BTF`** | — | ⚠️ **这套 config 跑不了 daed**（daed 要 BTF）。他们用 Passwall 所以无所谓。你如果改回 daed 记得别沿用 |
| `CONFIG_PACKAGE_airoha-en7581-npu-firmware=y` | =y | **就是 stock MT7992/eagle 那份**，见 §1.2 |
| `CONFIG_PACKAGE_kmod-airoha-paged-bosa=y` | =y | 你的 BOSA 型号已确认（GN28L95 / UX3363 分页式），与 `hg5585f-common.dtsi` 的 `fiberhome,hg5x-bosa` + `airoha,paged-bosa` 对应 |
| `CONFIG_PACKAGE_luci-app-pon-status` / `luci-app-natmode` | =y | 第三方 LuCI 卡片，见 §3.4 |
| `CONFIG_PACKAGE_zoneinfo-asia=y` | diy 追加 | 时区库（`diy-part2.sh` 动态追加） |
| `CONFIG_PACKAGE_iw=y` | diy 追加 | `iw`（`diy-part2.sh` 追加，因为 160MHz 能力检测需要） |

### 3.4 顺带值得关注的三个第三方 LuCI 包

`diy-part1.sh` 默认开 `ADD_AIROHA_NPU=true`（`luanmuc/luci-app-airoha-npu`）+ `ADD_LUCI_APP=true`（`qwe3017/luci-app` monorepo，含 `luci-app-pon-status` + `luci-app-natmode`）：

| 包 | 作用 | 对你的价值 |
|---|---|---|
| `luci-app-airoha-npu` | Airoha SoC 状态页：**NPU 卸载状态 / CPU 频率与超频 / Frame Engine / PPE 流表** | 🟢 **高**。你现在只能 `cat /sys/kernel/debug/ppe/entries` 数行数，这个给你图形化的 NPU/PPE 面板 + CPU 频率。选 `luanmuc` 版而非 `rchen14b` 原版的原因也很实在：自带 `po/zh_Hans` 48 条全翻、无「根目录+同名子目录」重复结构（那个结构会让 feed 索引中断） |
| `luci-app-pon-status` | 概览页「系统」下一格的 PON 光模块卡片：收光/发光/温度/偏置/电压 | 🟡 中。纯可观测，但比 tempinfo 一行更清楚 |
| `luci-app-natmode` | 「网络 → NAT 类型」三选一（NAT1/3/4） | 🟡 中。比手改 `kmod-nft-fullcone` + firewall 配置友好。注意上游修过一个坑：*「LuCI 保存时 rpcd 暂存值 CLI 读不到」→ 点了保存但模式没应用*，修法是 `apply <mode> [<fullcone6>] [<auto_offload>]` 支持显式传参 |

### 3.5 裁决

| 子项 | 收益 | 可移植性 | 风险 | 工作量 |
|---|---|---|---|---|
| 包索引方法论（`package/custom` + stamp） | 2/5 只在你加包时有用 | **5/5** 纯 buildroot 机制，与内核版本无关 | 1/5 | 1/5 记住即可 |
| `luci-app-airoha-npu` | **4/5** 终于能看见 NPU/PPE/CPU 频率 | 4/5 纯 LuCI + 读 debugfs/sysfs | 2/5 第三方包，需确认符号名对得上 6.18 | 2/5 clone + 一条 `CONFIG_PACKAGE_` |
| `luci-app-pon-status` / `natmode` | 3/5 | 4/5 | 2/5 | 2/5 |
| po 改名 / `LUCI_BASENAME` 陷阱 | 2/5 只在你自建 luci 包时遇到 | 5/5 | 1/5 | 1/5 |

---

## 4. `96-wifi-5g-cn` 做了什么

### 4.1 具体设了什么

对**所有 5G radio**（新版 `band='5g'`，旧版 `hwmode='11a'`）：

| UCI key | 值 |
|---|---|
| `wireless.<dev>.country` | **`CN`** |
| `wireless.<dev>.country_ie` | **`1`**（beacon 里广播国家码） |
| `wireless.<dev>.channel` | **`auto`**（ACS 自动选信道） |
| `wireless.<dev>.htmode` | **`HE160`**，能力不足则回落 **`HE80`** |

`HE160` 的判定逻辑：
```sh
support_160() {
	local phy="$1"
	[ -z "$phy" ] && return 1
	command -v iw >/dev/null 2>&1 || return 1
	iw phy "$phy" info 2>/dev/null | grep -qE '160 MHz|80\+80 MHz' || return 1
	return 0
}
# 取不到 phy 名时不检测（保持 HTMODE）—— 避免无 phy 选项的 radio 被误判回落
```
最后 `uci -q commit wireless`，**不重启无线**（注释：*「重载而非重启：避免首启期间无线中断后不可恢复」*——但**仓库里入库的那份没有 `wifi reload`**，`diy-part2.sh` 生成的版本才有，属两处漂移）。

### 4.2 是不是「信道/国家码修正」？

**部分是，但方向与你的需求相反。**
- 它做的确实是「国家码修正」（`CN` + `country_ie=1`）——**这一点你已经做了**，而且 AGENTS 里记着关键教训：*「country 必须设 `CN`，global 00 下 ch149 是 NO-IR」*。这条它和你一致。
- 但它把 **channel 设成 `auto`、频宽设成 `HE160`**——而你的现网是 **ch149 / HE80**，而且是**刻意选的**（ONU 5G 客户端实测全是 80MHz 或更低、无 160 客户端，降 80 对现有设备零损失，还避开与小米 AP 的 ch36/160 冲突）。

### 4.3 一个必须知道的副作用

脚本自己的 README 就写了：
> **DFS**：CN 法规下 160MHz 需要信道 36–64，其中 **52–64 属 DFS**。ACS 若选中，启动时会先做雷达检测（**CAC**），**WiFi 可能延迟 1–10 分钟才出现**或自动跳频。这是正常现象，不是故障。

对照你的现实：小米 AP 的 5G 已经在 **ch36/160**（CN 唯一 160 块）。两边都奔 160 会**直接抢同一块频谱**。

### 4.4 裁决

| 收益 | 可移植性 | 风险 | 工作量 |
|---|---|---|---|
| **1/5**（对你是负收益） | 3/5 脚本本身可移植，但你**已刷机**——这是**编译期首启默认值**，对现网机器只能手动 `uci set` | **4/5** HE160 触发 DFS/CAC（1–10 分钟无 WiFi）；与小米 AP ch36/160 抢频谱；`channel=auto` 让 ACS 每次可能换信道 | 1/5 |

**🔴 不要抄。** 唯一值得留的是「`country_ie=1` 显式广播」和「`support_160` 的能力探测思路」这两条。你的 ch149/HE80 是**更优解**，别被它的默认值带偏。

---

## 5. `feeds.conf.default`：有什么源？能不能解决 apk 404？

### 5.1 内容（原文）

```
src-git packages      https://github.com/immortalwrt/packages.git
src-git luci          https://github.com/immortalwrt/luci.git
src-git routing       https://github.com/openwrt/routing.git
src-git telephony     https://github.com/openwrt/telephony.git
src-git video         https://github.com/openwrt/video.git
src-git pon_drivers   https://github.com/pbs05/openwrt-pon-drivers.git
src-git pon_userspace https://github.com/pbs05/openwrt-pon-userspace.git
#src-git targets      https://github.com/openwrt/targets.git
#src-git oldpackages  http://git.openwrt.org/packages.git
#src-link custom      /usr/src/openwrt/custom-feed
# nikki：透明代理（mihomo 内核）+ LuCI 界面
src-git nikki         https://github.com/nikkinikki-org/OpenWrt-nikki.git;main
```

### 5.2 与 ponwrt 源码自带的逐行比对

我另外拉了 `pbs05/ponwrt` 的 `feeds.conf.default`：

| | ponwrt 自有 | qwpianzhang |
|---|---|---|
| packages / luci | immortalwrt | **同** |
| routing / telephony / video | openwrt | **同** |
| pon_drivers / pon_userspace | pbs05 | **同** |
| nikki | 无 | **+1 行（唯一新增）** |

**结论：这份文件 = ponwrt 原版 + 一行 nikki。** 它对「包源」这件事**没有任何新东西**。

### 5.3 能不能解决 apk 404？——**不能，而且它不是干这个的**

这是最容易误解的一点，必须讲清楚：

- `feeds.conf.default` 是 **编译期**的源码拉取清单（`./scripts/feeds update -a` / `install -a`），**不是运行时的 apk/opkg 仓库**
- 这个仓库**通篇没有任何运行时包源配置**。它的思路是**反向的**：既然找不到兼容的二进制源，就**把所有包都编译进固件**（`configs/*.config` 四百多行全是 `CONFIG_PACKAGE_xxx=y`，逐个把包烧进 rootfs）
- 所以它**不提供、也不追求**「刷完之后 `apk add` 能装东西」这个能力

你在 AGENTS 里记的真因是对的：**上游 25.12 起全切 apk**，opkg 源自然全 404。这个仓库帮不上——它自己也一样停在「编译期解决」这条路上。

**真正能借鉴的三条（这才是这个文件的价值）：**

1. **加包的正道是 `package/custom/` + 重扫索引，不是改 feeds.conf**（见 §3.2）。`src-link custom` 那行在文件里是**注释掉的**，并且 `diy-part1.sh` 用一整段注释论证了**为什么不该打开它**。
2. **第三方插件用 `git clone` 进 `package/custom`**，靠目录名当包名。这是绕开「没有 feed」的最省事办法。
3. **想要运行时 `apk add`，得自带同版本 apk 仓库 + 公钥**（`CONFIG_SIGNED_PACKAGES` / `CONFIG_SIGNATURE_CHECK` 那套）。ponwrt 是自定义构建，公网上没有与你 `VERSION_NUMBER` 精确匹配的 apk 索引——这就是 404 的本质。**要么自己搭一个 apk 仓库，要么老实编进固件。**

### 5.4 裁决

| 收益 | 可移植性 | 风险 | 工作量 |
|---|---|---|---|
| **1/5**（就多加一个 nikki feed） | 5/5 但你**不需要** | 1/5 | 1/5 |

**🔴 无移植价值。** 若你要用 nikki（mihomo 内核 + LuCI），加那一行就够。

### 5.5 顺带核对：CI 编排部分，你的 `build.yml` 已经基本对齐了

qwpianzhang 的 `build-ponwrt.yml`（545 行量级）里有不少设计，你本地 `firmware/ponwrt-hg5585f/.github/workflows/` 已经有了对应物。**逐条对照，避免重复造：**

| qwpianzhang 的做法 | 你的现状 | 结论 |
|---|---|---|
| 工具链缓存 key = `board-subtarget-tools/toolchain Makefile 哈希前16位` | `build.yml` 有「计算工具链缓存 key」步骤，同样对 `tools/ toolchain/` 做哈希 | ✅ 已有 |
| 工具链缓存三层回退（`actions/cache` → `toolchain-cache` Release → 本地编） | 有 `keep-cache-alive.yml`（对应它的 `cache-keepalive.yml`） | ✅ 已有 |
| 缓存命中后跳过工具链重编（它 `sed` 改 Makefile；后来改成 `touch stamp`） | — | ⚪ 若要确认，可用 `touch toolchain/stamp-compile tools/stamp-compile`（比 `sed` 干净，上游改缩进不会失效） |
| `dl` / `ccache` 缓存 key 用 **年+周号**（`date +%Y%W`），不用 `run_id` | 你的 `build.yml` 也用 `steps.meta.outputs.week` | ✅ 已有 |
| **ccache 陷阱**：`tools/Makefile` 的 `ifneq ($(CONFIG_CCACHE)$(CONFIG_SDK),)` 决定 ccache 二进制是否被编入 `staging_dir/host/bin`；工具链缓存若在「未开 ccache」时建立，命中后会跳过 `make tools/install` ⇒ `/bin/sh: ccache: not found (Error 127)` | 你**开了** `CONFIG_CCACHE=y`（`hg5585f-build.config` 第一项）且有「初始化 ccache」步骤（`ccache -M 4G`） | 🔴 **这个坑对你是真实存在的**。它给的两个保险值得照抄：① 缺二进制时 `make tools/ccache/install` 补装；② **补装失败自动把 `CONFIG_CCACHE` 改回 `is not set` 继续编译**（绝不因 ccache 让整次构建失败） |
| 并发数按可用内存算（每 cc1 约 1.5–2 G RSS，`-j8` 在 16 G runner 上易 OOM） | — | 🟡 值得抄那行 awk：`JOBS=$(awk -v p="$(nproc)" '/^MemAvailable:/{m=int($2/2097152)+1} END{print m<p?m:p}' /proc/meminfo)` |
| `make download` 失败重试 3 次 + 清理 `<1024 字节` 的残包（否则解压报 `does not look like a tar archive`） | — | 🟡 值得抄 |
| `fail_on_unmatched_files: false`（各机型产物后缀不同，缺哪种都别让 Release 失败） | — | 🟡 值得抄 |
| Release 保留最近 10 个（`delete_tag_pattern` 不误删 `toolchain-cache`） | 有 `release.yml` | ⚪ 看情况 |
| `scope=toolchain-only` 先预热工具链再出固件 | `build_recovery` 输入条 | ⚪ 概念对等 |

**这一段不需要移植代码，只需要补 3 个保险：ccache 失败自愈、`-j` 按内存、`download` 重试。**

---

## 6. 总评分表（收益 / 可移植性 / 风险 / 工作量）

> **收益** 5=显著省 CPU 或显著提稳；**可移植性** 5=直接可用；**风险** 5=可能变砖/丢数据/自启动失败；**工作量** 5=要搭环境+多次迭代。
> 打分是**针对你这台机器（HG5585F CU / mainline 6.18 / apk / 438MB）**，不是通用评价。

| # | 项目 | 收益 | 可移植 | 风险 | 工作量 | 一句话裁决 |
|---|---|:--:|:--:|:--:|:--:|---|
| 1 | **NPU clanker 固件「只换 bin」** | 3 | 4 | 3 | 2 | 🟡 修 E10/E1/E7；**唯一有实质内容的项** |
| 2 | NPU clanker「WiFi 卸载」（dtsi + kite） | 2 | 3 | **5** | 4 | 🔴 吃 110 MiB / 438MB，且 stock 镜像变体不匹配 |
| 3 | `strip-default-npu-fw.sh` 方法论 | 2 | **5** | 1 | 1 | 🟡 **目标是完整源码树 ⇒ 直接可用**（但要补 `.config` 那 3 行） |
| 4 | `tempinfo` 的 `ponctl --json` + `jsonfilter` | 3 | **5** | 1 | 1 | 🟢 抄，但你**已经在用** ⇒ 只需补 4 个字段 |
| 5 | `tempinfo` 的 4 个光模块字段 + `uci get` 设备探测 | 3 | 5 | 1 | 1 | 🟢 **10 分钟**，见 §0.2 |
| 6 | `luci-app-airoha-npu`（NPU/PPE/CPU 频率面板） | **4** | 4 | 2 | 2 | 🟢 **性价比最高的可视化** |
| 7 | `luci-app-pon-status` + `luci-app-natmode` | 3 | 4 | 2 | 2 | 🟡 顺手带上 |
| 8 | 包索引方法论（`package/custom` + 删 stamp） | 2 | 5 | 1 | 1 | 🟡 备查（你的树里还没有 `package/custom`） |
| 9 | po 改名 / `LUCI_BASENAME` 陷阱 | 2 | 5 | 1 | 1 | 🟡 自建 luci 包时必备 |
| 10 | `96-wifi-5g-cn`（CN/auto/HE160） | **1** | 3 | 4 | 1 | 🔴 **倒退**，你是 ch149/HE80 |
| 11 | `feeds.conf.default` (+nikki) | 1 | 5 | 1 | 1 | 🔴 与你问题无关（你的 `build.yml` 已管 feeds） |
| 12 | `diy-part1/2.sh` 的性能调优 | **0** | — | — | — | ⚪ **不存在**（一行都没有） |
| 13 | 固件版本号后缀 `%D %V · author · time` | 1 | 4 | 1 | 1 | ⚪ 纯观感 |
| 14 | **CI 编排本身**（工具链缓存 / dl 缓存按周号 / ccache 陷阱 / `fail_on_unmatched_files`） | 2 | 4 | 1 | — | ⚪ **你的 `build.yml` 已经做了**（见 §5.5） |

---

## 7. 可直接抄的代码片段（完整，标注来源文件）

### 7.1 【最高价值】`tempinfo` 的精确补丁（针对你现有 37 行版）

> 来源：`files/sbin/tempinfo`（`qwpianzhang/Actions-OpenWrt-HG5585F`）
> ⚠️ **修正**：你的 `files/sbin/tempinfo` **已经在用** `ponctl --json` + `@.frontend.temperature_celsius`。所以下面不是「替换」，而是**三处定点改造**。完整原文见本节末尾（供对照）。

#### 改造 A：光模块从「只有温度」扩到「温度+收发光+偏置+电压」

替换你现有第 25–29 行那段：
```sh
# ✅ 改后：一次取 JSON，四个字段复用同一次调用（原来每个字段都要重跑一次 ponctl）
PON_JSON=""
if [ -x /usr/sbin/ponctl ]; then
	pon_dev=""
	[ -x /sbin/uci ] && pon_dev="$(/sbin/uci -q get pon.@xpon[0].device 2>/dev/null)"
	if [ -n "$pon_dev" ]; then
		PON_JSON="$(/usr/sbin/ponctl --device "$pon_dev" status --json 2>/dev/null)"
	else
		PON_JSON="$(/usr/sbin/ponctl status --json 2>/dev/null)"
	fi
fi

# jsonfilter 取值；缺任一环节返回空（不报错）
jf() {
	[ -n "$PON_JSON" ] || return 0
	[ -x /usr/bin/jsonfilter ] || return 0
	printf '%s' "$PON_JSON" | /usr/bin/jsonfilter -q -e "$1" 2>/dev/null
}

# 浮点 → 保留 1 位（温度，与 CPU/WiFi 的 %.1f 一致）
f1() { [ -n "$1" ] && awk -v v="$1" 'BEGIN { printf("%.1f", v) }' 2>/dev/null; }
# 浮点 → 保留 2 位（功率/电流/电压）
f2() { [ -n "$1" ] && awk -v v="$1" 'BEGIN { printf("%.2f", v) }' 2>/dev/null; }

pon="" pon_tx="" pon_rx="" pon_bias="" pon_volt=""
if [ -n "$PON_JSON" ]; then
	pon_temp="$(f1 "$(jf '@.frontend.temperature_celsius')")"
	[ -n "$pon_temp" ] && pon="PON: ${pon_temp}°C"
	pon_tx="$(f2 "$(jf '@.frontend.tx_power_dbm')")"
	pon_rx="$(f2 "$(jf '@.frontend.rx_power_dbm')")"
	pon_bias="$(f2 "$(jf '@.frontend.tx_bias_ma')")"
	pon_volt="$(f2 "$(jf '@.frontend.voltage_volts')")"
	[ -n "$pon_tx" ]   && pon="$pon ↑${pon_tx}dBm"
	[ -n "$pon_rx" ]   && pon="$pon ↓${pon_rx}dBm"
	[ -n "$pon_bias" ] && pon="$pon ${pon_bias}mA"
	[ -n "$pon_volt" ] && pon="$pon ${pon_volt}V"
fi
```

**为什么值得抄这段的注释**（`ponctl` 已经把 SFF-8472 换算做完了，别自己解析 i2c）：
```
#   temperature_8472 ÷ 256      → temperature_celsius (°C)
#   tx_power_8472 → 10log10−40  → tx_power_dbm        (dBm)
#   rx_power_8472 → 10log10−40  → rx_power_dbm        (dBm)
#   tx_bias_8472  × 0.002       → tx_bias_ma          (mA)
#   voltage_8472  × 0.0001      → voltage_volts       (V)
```

#### 改造 B：WiFi 温度补一条 hwmon 路径（你现有第 20 行漏了）

```sh
# ❌ 现在只有这一条
for f in /sys/class/ieee80211/phy*/hwmon*/temp1_input; do

# ✅ mt76 的 hwmon 有两种挂法，两条都要试
for f in /sys/class/ieee80211/phy*/hwmon*/temp1_input \
         /sys/class/ieee80211/phy*/device/hwmon/hwmon*/temp1_input; do
	[ -r "$f" ] || continue
	wifi="$wifi$(awk '{printf "%.1f°C ", $1/1000}' "$f")"
done
```

#### 改造 C：设备名不要硬编码 `pon0`

你现有第 26 行是 `ponctl --device pon0 status --json`。若哪天接口改名（或换 `pon0.995` 之外的形态）就**静默失效**（`[ -n "$t" ]` 判空，什么都不显示、也不报错）。用 `uci -q get pon.@xpon[0].device` 探测 + 无值时不传 `--device`（见改造 A）。

#### 完整原文（对照用，来源 `files/sbin/tempinfo`）

```sh
#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# /sbin/tempinfo —— 概览页「温度」行数据源
#
# 调用链：
#   luci-mod-status/.../include/10_system.js
#     → callTempInfo() → rpcd 方法 luci.getTempInfo → 执行 /sbin/tempinfo
#     → 输出非空则在「系统」表格插入「温度」行（if (tempinfo.tempinfo)）
#
# 为什么需要本文件：
#   autocore 的 Makefile 只在 ipq% / mediatek% / qualcommax% 这几个 TARGETID
#   下安装 files/tempinfo，airoha(AN7581/AN7583) 不在列表内，
#   故 ponwrt 原生固件无 /sbin/tempinfo，概览页没有温度行。
#   本文件经 files/ 覆盖进 rootfs 补齐。
#
# 授权：无需额外 ACL。autocore 装的
#   /usr/share/rpcd/acl.d/luci-mod-status-autocore.json
#   无条件授权 luci.getCPUInfo / luci.getTempInfo（受限的只是 tempinfo 脚本本身）。
#
# 输出示例：
#   CPU: 58.7°C, WiFi: 46.0°C 48.0°C, PON: 48.5°C ↑2.41 ↓-21.30 dBm 12.50 mA 3.30 V

IEEE_PATH="/sys/class/ieee80211"
THERMAL_PATH="/sys/class/thermal"

# 是否在「温度」行附带 PON 光功率 / 偏置电流 / 电压。
# 1 = 附带（一行显示全套）；0 = 只显示温度。
SHOW_PON_OPTICS=0

fmt_c() { [ -r "$1" ] && awk '{printf("%.1f°C", $0 / 1000)}' "$1" 2>/dev/null; }

PON_JSON=""
if [ -x /usr/sbin/ponctl ]; then
	pon_dev=""
	if [ -x /sbin/uci ]; then
		pon_dev="$(/sbin/uci -q get pon.@xpon[0].device 2>/dev/null)"
	fi
	if [ -n "$pon_dev" ]; then
		PON_JSON="$(/usr/sbin/ponctl --device "$pon_dev" status --json 2>/dev/null)"
	else
		PON_JSON="$(/usr/sbin/ponctl status --json 2>/dev/null)"
	fi
fi

jf() {
	[ -n "$PON_JSON" ] || return 0
	[ -x /usr/bin/jsonfilter ] || return 0
	printf '%s' "$PON_JSON" | /usr/bin/jsonfilter -q -e "$1" 2>/dev/null
}

# CPU 温度
cpu_temp=""
if [ -r "$THERMAL_PATH/thermal_zone0/temp" ]; then
	cpu_temp="$(fmt_c "$THERMAL_PATH/thermal_zone0/temp")"
fi

# WiFi 温度（mt76 / MT7916）—— 两种 hwmon 挂法都试
wifi_temp=""
for p in "$IEEE_PATH"/phy*/hwmon*/temp1_input \
         "$IEEE_PATH"/phy*/device/hwmon/hwmon*/temp1_input; do
	[ -r "$p" ] || continue
	t="$(fmt_c "$p")"
	[ -n "$t" ] && wifi_temp="${wifi_temp:+$wifi_temp }$t"
done

# PON 光模块
pon_temp="" pon_tx="" pon_rx="" pon_bias="" pon_volt=""
if [ -n "$PON_JSON" ]; then
	pon_temp="$(f1 "$(jf '@.frontend.temperature_celsius')")"
	if [ "$SHOW_PON_OPTICS" = "1" ]; then
		pon_tx="$(f2 "$(jf '@.frontend.tx_power_dbm')")"
		pon_rx="$(f2 "$(jf '@.frontend.rx_power_dbm')")"
		pon_bias="$(f2 "$(jf '@.frontend.tx_bias_ma')")"
		pon_volt="$(f2 "$(jf '@.frontend.voltage_volts')")"
	fi
fi

# 组装
out=""
[ -n "$cpu_temp" ] && out="CPU: $cpu_temp"
[ -n "$wifi_temp" ] && out="${out:+$out, }WiFi: $wifi_temp"

if [ -n "$pon_temp" ]; then
	pon="PON: ${pon_temp}°C"
	[ -n "$pon_tx" ]   && pon="$pon ↑${pon_tx}dBm"
	[ -n "$pon_rx" ]   && pon="$pon ↓${pon_rx}dBm"
	[ -n "$pon_bias" ] && pon="$pon ${pon_bias}mA"
	[ -n "$pon_volt" ] && pon="$pon ${pon_volt}V"
	out="${out:+$out, }$pon"
fi

[ -n "$out" ] || out="No temperature info"

printf '%s' "$out"
```

> **你的 `SHOW_PON_OPTICS` 该设 `1`**：你没有 `luci-app-pon-status` 卡片，不会重复显示。
> **开销提醒**（原文注释）：概览页轮询 3 秒 ⇒ `tempinfo` 每 3 秒跑一次 `ponctl`。`ponctl` 是 Rust 二进制、只读 sysfs，开销可忽略；但**别在 `tempinfo` 里再加高开销命令**（它也提醒：若同时装 `luci-app-pon-status`，两者叠加约每 1.5 秒一次 `ponctl`）。

#### 先验证字段存在（一步）

```sh
ponctl status --json | head -40      # 确认 @.frontend.tx_power_dbm 等四个字段真有
```

---

---

### 7.2 【方法论】让本地包进入 buildroot 索引（不注册 feed）

> 来源：`diy-part1.sh`（注释 + 校验逻辑）

```sh
PKG_DIR="package/custom"
mkdir -p "$PKG_DIR"

# 强制重建索引
#   只删 tmp/.packageinfo 不够：prepare-tmpinfo 有 scan_unchanged 优化
#   （拿 tmp/info/.scan-*.stamp 比 mtime），stamp 还在且没有更新的 Makefile
#   时会跳过扫描 —— 结果 .packageinfo 被删了却没人重建，索引反而空了。
rm -f tmp/.packageinfo tmp/.targetinfo
rm -f tmp/info/.scan-packageinfo.stamp tmp/info/.scan-targetinfo.stamp
rm -f tmp/.config-package.in tmp/.config-target.in

make -s prepare-tmpinfo OPENWRT_BUILD= 2>&1 | tail -5 || true

# 判据：tmp/.packageinfo（不是 package/feeds/custom，那个不存在是正常的）
for d in "$PKG_DIR"/*; do
  [ -d "$d" ] || continue
  n=$(basename "$d")
  if grep -qx "Package: $n" tmp/.packageinfo 2>/dev/null; then
    echo "  ✅ $n"
  else
    echo "  ❌ $n —— tmp/.packageinfo 里查不到"
    # 真实错误在这里（scan.mk 落盘路径）
    for f in "logs/package/$n/dump.txt" "logs/package/custom/$n/dump.txt"; do
      [ -f "$f" ] && { echo "===== $f ====="; tail -25 "$f"; }
    done
  fi
done
```

**清理重复嵌套目录**（`rchen14b/luci-app-airoha-npu` 那类仓库会导致整个 custom feed 索引中断）：
```sh
for d in "$PKG_DIR"/*; do
  [ -d "$d" ] || continue
  n=$(basename "$d")
  if [ -d "$d/$n" ] && [ -f "$d/$n/Makefile" ]; then
    rm -rf "$d/$n"
    echo "✅ 已移除重复嵌套目录: $n/$n"
  fi
done
```

---

### 7.3 【自建 luci 包必备】po 文件必须按 `LUCI_BASENAME` 命名

> 来源：`diy-part1.sh`

```sh
# luci.mk 的 i18n install 规则：
#   po2lmo $(po) → $(LUCI_LIBRARYDIR)/i18n/$(basename $(notdir $(po))).$(lang).lmo
# 即 lmo 名取自 po 文件主名。而运行时按
#   LUCI_BASENAME = $(patsubst luci-app-%,%,luci-app-airoha-npu) = airoha-npu
# 查找 lmo。上游两份 po 都叫 luci-app-airoha-npu.po，
# 会生成 luci-app-airoha-npu.zh-cn.lmo，前端找不到 → 中文不生效。
PODIR="$PKG_DIR/luci-app-airoha-npu/po"
if [ -f "$PODIR/zh_Hans/luci-app-airoha-npu.po" ]; then
  # 确保 Language 头是 zh_Hans
  grep -q '^"Language:' "$PODIR/zh_Hans/luci-app-airoha-npu.po" || \
    sed -i 's/^msgstr ""$/msgstr ""\n"Language: zh_Hans\\n"/' "$PODIR/zh_Hans/luci-app-airoha-npu.po"
  mv "$PODIR/zh_Hans/luci-app-airoha-npu.po" "$PODIR/zh_Hans/airoha-npu.po"
fi
```

---

### 7.4 【验证用】确认当前 NPU 固件到底是谁的

> 来源：`scripts/build-npu-fw.sh` + ClankerNPU README（`GITREV` 打进 boot 的 `NPU Version` 行）

```sh
# 1) 当前固件版本 + NPU 是否 probe 成功
dmesg | grep -i npu
#   预期（你现在）：NPU fw version: 1456.62
#   换成 clanker 后：NPU Version 行会带 git hash（如 ... <short-sha>），版号格式明显不同

# 2) 两个 bin 是否在位、大小是否在限内
ls -l /lib/firmware/airoha/
#   en7581_npu_rv32.bin  ≤ 2097152 (2 MiB)
#   en7581_npu_data.bin  ≤ 65536   (64 KiB)

# 3) PPE 是否真的挂上了 NPU
cat /sys/kernel/debug/ppe/config | grep npu_attached     # → npu_attached: 1
wc -l /sys/kernel/debug/ppe/entries                      # → 你实测 328

# 4) 缺文件/名字不对的表现（供排错）
#    request_firmware_direct() 返回 -ENOENT → 驱动映射成 -EPROBE_DEFER
#    → NPU 一直不绑定，deferred probe pending 里能看到具体文件名
#    大小超限 → 直接 -E2BIG

# 5) 大小不匹配 / 变体不匹配时，检查 WiFi 卸载有没有试图初始化
dmesg | grep -iE 'npu_bridge|wlan_init|is_wifi_link_up'
```

---

### 7.5 【仅在真要换固件时】strip-default-npu-fw 的核心逻辑

> 来源：`scripts/strip-default-npu-fw.sh`
> ⚠️ **不要直接跑它**——它改的是 `target/linux/airoha/**`，跑之前先 `git diff` 确认。这里是备查其 perl 续行处理思路。

```sh
PONWRT_DIR="${PONWRT_DIR:-.}"
STRICT="${STRICT:-0}"
cd "$PONWRT_DIR"

STRIP_RE='airoha-[A-Za-z0-9_.-]*npu-firmware'

perl -e '
my $STRIP_RE = qr/airoha-[A-Za-z0-9_.-]*npu-firmware/;
my ($modified, $residual) = (0, 0);
for my $f (@ARGV) {
    open(my $fh, "<", $f) or next;
    local $/; my $c = <$fh>; close $fh;
    my @lines = split(/(?<=\n)/, $c);
    my @out; my $in = 0; my $changed = 0; my $ln = 0;
    for my $l (@lines) {
        $ln++;
        # 进入包列表赋值（含 = := += ?= != 等）
        if ($l =~ /^[ \t]*(?:DEFAULT_PACKAGES|DEVICE_PACKAGES)[ \t]*[+:?!]?=/) { $in = 1; }
        if ($in && $l =~ /$STRIP_RE/) {
            $l =~ s/[ \t]*$STRIP_RE\b//g;      # 只摘 npu 固件，其余包原样保留
            $changed = 1;
        }
        # 行尾没有续行反斜杠 -> 这一段结束（关键：必须跟踪续行）
        if ($in && $l !~ /\\\s*\n?$/) { $in = 0; }
        push @out, $l;
    }
    if ($changed) {
        open(my $w, ">", $f) or die "write $f: $!";
        print $w join("", @out); close $w;
        $modified++; print "[MODIFIED] $f\n";
    }
}
print "[SUMMARY] modified=$modified\n";
' $(grep -rlE '(DEFAULT_PACKAGES|DEVICE_PACKAGES)' target/ 2>/dev/null || true)
```

---

### 7.6 【若要自己编】换固件的完整命令（WSL / Linux）

> 来源：`scripts/build-npu-fw.sh` 的用法注释 + `gen-npu-fw-package.sh` 环境变量表

```bash
# 前提：x86-64 Linux（WSL 可），有 git/curl/tar/make，能访问 GitHub Releases
# 输出：两个 bin，直接 scp 到路由器 /lib/firmware/airoha/ 覆盖即可
#       （ponwrt 用的是默认前缀 en7581，不需要改 DTS、不需要 firmware-name）

SOC=AN7581 WIFI=MT7916 CLANKER=0 ./scripts/build-npu-fw.sh
#   → files/lib/firmware/airoha/en7581_npu_rv32.bin
#   → files/lib/firmware/airoha/en7581_npu_data.bin
#   脚本会自动：下载 xpack riscv-none-elf-gcc 14.2.0-3 (~100MB) → clone ClankerNPU
#              → make CROSS=riscv-none-elf- → 体积自检（超限直接失败）
#
# ⚠️ CLANKER 必须 0：1 会加 -DUSE_CLANKER_DRIVER，是配 Clanker 自改 host driver 用的，
#    配 stock/mainline 驱动会坏
# ⚠️ 想钉死版本（强烈建议）：加 CLANKER_REF=<commit sha>
#    上游明说 npu_src_ref 默认跟 main 最新 ⇒ 不同时间编出的固件可能不同、无法复现
```

**回滚**（先在路由器上做）：
```sh
mkdir -p /root/npu-fw-backup
cp /lib/firmware/airoha/en7581_npu_*.bin /root/npu-fw-backup/
sha256sum /root/npu-fw-backup/*
dmesg | grep -i npu > /root/npu-fw-backup/dmesg-before.txt
# 覆盖 → 重启 → 对比 dmesg 与 npu_attached / ppe/entries 行数
```

---

## 8. 对 ponwrt（mainline 6.18 + apk）不适用 / 需改造的清单

| 项目 | 状态 | 原因 |
|---|---|---|
| **`npu_fw=clanker` 整套 CI 流程** | 🔴 **不可直接搬** | 那是 GitHub Actions 编排（`strip` → `diy1` → `build pkg` → `reindex` → `load config` → `select pkg` → `defconfig`）。**你已刷机**，这条流水线对你无用；只有 `build-npu-fw.sh` 产出的两个 bin 有用 |
| **`an7581-npu-wlan.dtsi`（WiFi 卸载）** | 🔴 **不适用** | 吃 **110 MiB / 438MB ≈ 25%**；且 ponwrt 里 stock 固件是 MT7992(eagle)、板载 MT7916(kite)，**变体不匹配，加了也白加**。dtsi 自身注释明写「不跑 Airoha 卸载 WiFi 的板子**不得**保留这些区」 |
| `strip-default-npu-fw.sh` 全量 | 🟡 **需改造** | 它依赖 ponwrt 源码树里的 `target/linux/airoha/**`。你若不用 apt/opkg 那条构建链，只在「自己重编固件」时才有意义。**已刷机的现网只需换 bin，不需要它** |
| `96-wifi-5g-cn` | 🔴 **不适用 / 反向** | ① 是**编译期首启默认值**，对已刷机机器只能手 `uci set`；② `HE160` + `channel=auto` 对你是倒退（你 ch149/HE80，且小米 AP 占 ch36/160）；③ DFS/CAC 会导致重启后 1–10 分钟无 5G |
| `feeds.conf.default`（含 nikki） | 🔴 **与问题无关** | 纯**编译期**源码清单，不是运行时 apk 仓库。**解决不了 apk/opkg 404**；唯一新增只有 nikki 一行 |
| `diy-part1.sh` 的插件 clone 清单 | 🟡 **需按需裁剪** | passwall / openclash / mosdns / lucky / tailscale / openlist / smartdns **默认全关**。你现在用 Passwall（xray+sing-box），若重编要注意它 clone 的是 `main` 分支，版本会漂 |
| `configs/*.config` 直接当 `.config` | 🔴 **不可直接搬** | ① 它是 **diffconfig**（约 440 行），必须 `make defconfig` 展开；② **无 `CONFIG_KERNEL_DEBUG_INFO_BTF`** ⇒ 沿用会**跑不了 daed**；③ `CONFIG_PKG_FORTIFY_SOURCE_1`（不是 2/3）、`SSTRIP`、`MOLD` 是体积取向，与你现状不同 |
| `luci-app-*` 三个第三方包 | 🟢 **可搬** | 纯 LuCI，但需确认符号名与 6.18 / 你当前 luci 版本对得上。**你的树里还没有 `package/custom/`**，要先建 |
| `tempinfo` | 🟢 **可搬（只需补字段）** | 你**已经**在用 `ponctl --json`，见 §0.2 修正 3 与 §7.1 的三处定点改造 |
| 固件版本号后缀 | ⚪ **可选** | 纯观感；但 `perl + 环境变量`避开 sed 分隔符的写法值得学（作者名里带 `/ \| # &` 不会炸） |
| **`scripts/*.sh` 那 4 个 NPU 脚本** | 🟡 **`strip` 可直接用；其余 3 个不必** | 你是完整源码树 ⇒ `strip-default-npu-fw.sh` 直接可跑。但 `apply-npu-dts.sh` 要生成的东西 `target/linux/airoha/dts/` 里**已有现成 dtsi**（`an7581-npu-mt7992.dtsi` / `mt7996.dtsi`），不必生成；`gen-npu-fw-package.sh` 是给 GitHub Actions 用的编排，你有 `kmerge.py` + `hg5585f-build.config` 覆盖层，更干净 |

---

## 9. 建议落地顺序（按性价比排序）

> 排序依据 = 收益 ÷（风险 × 工作量）。**前 3 项全是零风险/零内存代价的。**
> 已按 §0.2 的「目标是完整源码树」修正落地位置（全部改 `files/` 或 `configs/hg5585f-build.config`，**不改上游 target 树**）。

### 🥇 第 1 步：给 `files/sbin/tempinfo` 补 4 个光模块字段（10 分钟，零风险）

**不是重写**——你已有 `ponctl --json` 和 `@.frontend.temperature_celsius`。按 §7.1 的改造 A/B/C 打三处补丁：
① 加 `tx_power_dbm` / `rx_power_dbm` / `tx_bias_ma` / `voltage_volts`（一次 `ponctl` 调用取全部，别每字段重跑）
② WiFi 温度补 `/sys/class/ieee80211/phy*/device/hwmon/hwmon*/temp1_input` 这条路径
③ 把硬编码的 `--device pon0` 换成 `uci -q get pon.@xpon[0].device` 探测
**先跑 `ponctl status --json | head -40` 确认那四个字段真的存在**——这是唯一的前置条件。
⚠️ 概览页 3 秒一次，别在 `tempinfo` 里加别的高开销命令。

### 🥈 第 2 步：装 `luci-app-airoha-npu`（30 分钟，低风险）

这是**唯一能直接看见 NPU 卸载状态 / PPE 流表 / CPU 频率**的手段——你现在只能 `wc -l /sys/kernel/debug/ppe/entries`。
用 `luanmuc/luci-app-airoha-npu`（**不要** `rchen14b` 原版：自带 `po/zh_Hans` 48 条全翻、无「根目录+同名子目录」重复结构），clone 到 `package/custom/luci-app-airoha-npu`（**目录要先建**），按 §7.3 改 po 名，在 `configs/hg5585f-build.config` 加：
```
CONFIG_PACKAGE_luci-app-airoha-npu=y
CONFIG_PACKAGE_luci-i18n-airoha-npu-zh-cn=y
```
**装完立刻能验证的一件事**：PPE 流表里 IPv4/IPv6/VLAN 995/代理出口 IP 各占多少——这决定第 4 步值不值得做。

### 🥉 第 3 步：排查 E10（30 分钟，只读，零风险）

**在决定要不要换固件之前先做这个。** 目标是判断「E10 在你这台机器上是静默踩了内存，还是在 NPU 侧取数异常」：

```sh
# 3a. USB 口是否都在（E10 的触发条件是「package 缺端口」）
dmesg | grep -iE 'usb|xhci'
ls /sys/bus/usb/devices/
# 你的 DTS 开了 usb0(USB3) + usb1(USB2-only)，E10 描述「每个缩减版 package 都缺 USB port 2」

# 3b. NPU 侧有没有异常痕迹（E7 的「hart 冻死」会留下 mcause/mepc/mtval/ra/sp）
dmesg | grep -iE 'npu|hart|mcause|trap|exception'
cat /sys/kernel/debug/ppe/config

# 3c. host DRAM 有没有诡异的「随机一个内存字被改」
#     跑一次长时内存校验（438MB 机器，用 200MB 左右测）
memtester 200M 1        # 若没装：apk add memtester（或先编进固件）
#     对比：重启后连续跑 3 次，若同一物理位置反复出错 → 强烈怀疑 E10
```
**判据**：
- `memtester` 三轮**全过** + dmesg 无 NPU 异常 ⇒ E10 未造成可见损害，**第 4 步优先级下降，可缓做**
- `memtester` 报错 / dmesg 有 NPU trap ⇒ **E10 命中，第 4 步升级为必做**

### 4️⃣ 第 4 步：换 NPU 固件（半天，中等风险，**视第 3 步结果决定**）

**只做「换 bin」，不碰 DTS。**

```bash
# 4a. 一次性环境：WSL Ubuntu 22.04+ / 任意 x86-64 Linux
SOC=AN7581 WIFI=MT7916 CLANKER=0 CLANKER_REF=<钉死的 commit sha> \
  ./scripts/build-npu-fw.sh
```
**四个必须遵守的铁律：**
1. **`CLANKER=0`** —— `1` 是配 Clanker 自改 host 驱动，配 stock/mainline 驱动会坏
2. **`CLANKER_REF` 钉 commit sha**，不要用默认 `main` —— 上游明说「不同时间编出的固件可能不同，且没法复现」
3. **`WIFI=MT7916`**（kite）—— 与板载 MT7916D 一致。但注意：**你现在的 stock 是 MT7992/eagle**，所以这次换的不只是「同一变体的另一版」，而是**同时把数据面从 eagle 换成 kite**。有线 PPE 路径不受影响（PPE 是 host 侧 frame engine 的，与 NPU 的 WiFi 数据面无关），但这是本次换固件**最大的不确定性**，务必按 4b 逐步验证
4. **不动 `apply-npu-dts.sh`** —— 不加那 110 MiB

```sh
# 4b. 部署与验证（每步都要通过再往下；完整校验命令见 §7.4）
mkdir -p /root/npu-fw-backup
cp /lib/firmware/airoha/en7581_npu_*.bin /root/npu-fw-backup/
dmesg | grep -i npu > /root/npu-fw-backup/dmesg-before.txt
wc -l /sys/kernel/debug/ppe/entries >> /root/npu-fw-backup/dmesg-before.txt
free -m >> /root/npu-fw-backup/dmesg-before.txt

# scp 两个新 bin 上去覆盖 → 重启
dmesg | grep -i npu                      # ① NPU Version 行应变成带 git hash 的格式
cat /sys/kernel/debug/ppe/config | grep npu_attached   # ② 必须是 1
wc -l /sys/kernel/debug/ppe/entries                    # ③ 应恢复到你原来的量级（328 左右）
free -m                                                # ④ 可用内存不应变化（没加 dtsi）
# ⑤ 业务回归：有线 8 路并发测速，四核 busy 应仍在 5% 以内
# ⑥ WiFi 回归：5G ch149 HE80 关联、漫游、吞吐
```
**任一不符立即从 `/root/npu-fw-backup/` 还原两个 bin 并重启。**

### 5️⃣ 第 5 步（可选）：`luci-app-pon-status` + `luci-app-natmode`（20 分钟）

`qwe3017/luci-app` monorepo，clone 后拷两个子目录到 `package/custom`。
`natmode` 注意上游已修「LuCI 保存时 rpcd 暂存值 CLI 读不到 → 点了保存但模式没生效」的坑，**要用带 `apply <mode> [<fullcone6>] [<auto_offload>]` 显式传参的版本**。

### 6️⃣ 明确**不做**的清单

| 不做 | 原因 |
|---|---|
| ❌ **`an7581-npu-wlan.dtsi` / WiFi 卸载** | 110 MiB / 438MB ≈ **25% 内存**换「本来就不忙的 WiFi 转发」。**性价比为负** |
| ❌ **`96-wifi-5g-cn` 的 HE160 + auto** | 你的 ch149/HE80 是**更优解**；HE160 触发 DFS/CAC（1–10 分钟无 5G）并与小米 AP ch36/160 抢频谱 |
| ❌ **改 `feeds.conf.default` 指望修 apk 404** | 它是编译期源码清单，**不是运行时仓库**。要 `apk add` 只能用自带 apk 仓库 + 公钥，否则老实编进固件 |
| ❌ **整套 GitHub Actions 编排** | 你已刷机，流水线对你无用 |
| ❌ **`npu_clanker=1`** | 需要同时换 host 驱动，配 stock/mainline 驱动会坏 |

---

## 10. 未验证项与残留未知（诚实清单）

| # | 未确认的事 | 影响 | 建议怎么确认 |
|---|---|---|---|
| 1 | `1456.62` 到底是厂商版号还是某版 clanker | 决定「换固件」是不是真的换了东西 | 换之前 `dmesg \| grep -i npu` 全文留档；clanker 的 boot 行带 git hash，格式可辨 |
| 2 | **E10 在 512MB 机器上的实际表现**（踩 DRAM 还是取数异常） | 决定第 4 步是「必做」还是「可缓」 | §9 第 3 步的 `memtester` + dmesg 组合 |
| 3 | ClankerNPU 在 **AN7581 + MT7916(kite)** 上的验证状态 | 上游 `Verified paths` **只列了 AN7583+MT7993**，AN7581 kite **未列入** | 这是本次最大风险来源。可先在**非生产**方式下试（或先只验证 `npu_attached=1` + PPE 不受影响） |
| 4 | ponwrt 是否自带运行时 apk 仓库文件 | 影响「apk add 能不能用」的判断 | 实机 `cat /etc/apk/repositories`（比猜源码路径靠谱） |
| 5 | 你的 `ponctl` 是否支持 `status --json`（版本差异） | 第 1 步能否直接落地 | `ponctl status --json \| head` 一试便知 |
| 6 | `luci-app-airoha-npu` 的 debugfs 路径是否与 6.18 一致 | 装上了但面板空白 | 装完对照 `ls /sys/kernel/debug/ppe/` 与 `/sys/kernel/debug/` 下 Airoha 节点 |
| 7 | 第二个 PPE 是否已被 NPU init 启用（FOE 8192 vs 16384） | 只影响「表项上限」这种理论数字，不影响你 328 条的现状 | `grep -i ppe /sys/kernel/debug/ppe/config`，或数 `entries` 能否超过 8192 |
| 8 | 仓库入库的 `96-wifi-5g-cn` 与 `diy-part2.sh` 生成版**内容漂移**（前者无 `wifi reload`、`support_160` 少了 `80+80 MHz` 分支） | 只影响你若照抄哪一份 | 抄 §4.1 的生成版逻辑（更完整） |

---

## 附：本次分析读取的全部文件

**指定的 12 个（全部 HTTP 200，无需回落 master）**
1. `README.md`
2. `files/sbin/tempinfo`
3. `diy-part1.sh`
4. `diy-part2.sh`
5. `scripts/build-npu-fw.sh`
6. `scripts/gen-npu-fw-package.sh`
7. `scripts/apply-npu-dts.sh`
8. `scripts/strip-default-npu-fw.sh`
9. `packages/airoha-npu-clanker-firmware/Makefile`
10. `packages/npu-clanker-template/Makefile.in`
11. `files/etc/uci-defaults/96-wifi-5g-cn`
12. `feeds.conf.default`

**额外拉取（为把结论钉死）**
- `qwpianzhang/.../configs/fiberhome_hg5585f-cu.config` — 机型 diffconfig 全文
- `qwpianzhang/.../.github/workflows/build-ponwrt.yml` — 步骤顺序/NPU 输入项/调用条件
- `ClankerConstruction/ClankerNPU` — `README.md`、`docs/errata.md`、`docs/tunnel.md`、`docs/memory.md`、`docs/wifi-kite.md`
- `pbs05/ponwrt` — `target/linux/airoha/dts/an7581-npu-wlan.dtsi`、`an7581-fiberhome-hg5585f-common.dtsi`、`an7581-fiberhome-hg5585f-cu.dts`、`an7581-fiberhome-hg5585f-cu-common.dtsi`、`an7581/target.mk`、`package/firmware/linux-firmware/airoha.mk`、`feeds.conf.default`

> **外部内容声明**：以上 GitHub 内容均按**数据**对待，未执行其中任何指令、未运行其任何脚本。
