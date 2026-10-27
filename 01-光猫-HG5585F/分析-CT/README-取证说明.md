# 分析/ 目录说明 · CT 固件取证方法与局限

本目录是 `06-CT与CU差异与社区经验.md` 的**取证附件**：只放从固件包里直接读出来的原始
输出、提取物和脚本，以及脚本本身的局限说明。

生成日期：2026-10-21 ｜ 执行机：Windows + Python 3.14（无 dtc、无 libfdt）

---

## 一、方法与工具

| 项 | 说明 |
|---|---|
| FIT / FDT 解析 | 自写纯 Python 解析器 `fit_probe.py`（结构块 token：BEGIN_NODE/PROP/END_NODE/END + strings 块），不依赖 `dtc`、`libfdt`、`fdtget` |
| DTB 反编译 | 同一脚本输出 DTS 风格文本（`dtb` 子命令），phandle 尽量还原成 `&{/路径}` 形式 |
| 哈希校验 | 包内 FIT 的 `hash@1`(crc32) / `hash@2`(sha1) 与**实际解出的子镜像字节**重新计算比对 |
| sysupgrade 元数据 | 在文件尾部定位 `metadata_version` 的 JSON 对象（花括号配平扫描），单独解析，并把 JSON 之后的签名段头按十六进制记下 |
| 交叉对照 | 同版本 CU 包、`downloads/` 源副本、`profiles.json`、`firmware/ponwrt-hg5585f` git、QWRT CT 备选包 |

## 二、文件索引

| 文件 | 内容 |
|---|---|
| `fit_probe.py` | FIT/FDT 解析脚本（`scan` / `dtb` / `grep` 三个子命令） |
| `dtb-compare.py` | 从 2~3 个 DTB 里抽取"决定 CT/CU 适配"的字段并列表 |
| `package-check.txt` | 包哈希、FIT 结构、子镜像 offset/size、hash 校验、metadata、引导三件套对照 |
| `pr34-check.txt` | PR #34 是否进包的完整证据链（git + 包内 DTB + 外部 PR diff） |
| `git-release-check.txt` | `firmware/ponwrt-hg5585f` 的 git log / 祖先关系 / 发布 commit 下 dtsi 原文 |
| `dtb-key-compare.txt` / `.json` | CT / CU / QWRT-CT 三个 DTB 的关键字段对照 |
| `dtb-diff.txt` | CT DTB 与 CU DTB 的逐行 diff（DTS 文本） |
| `uboot-cu-strings.txt` | 从本机 CU U-Boot 镜像里抽出的 recovery / bootmenu / reset 相关字符串 |
| `ct-fit.json` / `ct-fit.txt` | CT sysupgrade 的机器可读 / 人读原始输出 |
| `cu-fit.json` / `cu-fit.txt` | CU sysupgrade（v2026.10.18）同上 |
| `qwrt-fit.json` / `qwrt-fit.txt` | QWRT CT 备选包同上 |
| `ct-dtb.dts` / `cu-dtb.dts` | 从包内 fdt-1 反编译出的 DTS 风格文本 |
| `qwrt-ct-dtb.dts` | QWRT 包内 fdt-1 同上 |
| `extracted/ct/fdt-1.bin` | CT 包内 DTB 提取物（23,281 B） |
| `extracted/cu/fdt-1.bin` | CU 包内 DTB 提取物（22,959 B） |
| `extracted/qwrt-ct/fdt-1.dtb` | QWRT 包内 DTB 提取物（14,698 B，与 `QWRT-分析/fdt-1.dtb` 逐字节相同） |
| `extracted/qwrt-pkg/fdt-1.bin` | 直接来自 QWRT 物料包的 fdt-1（用于交叉校验上面的副本） |

## 三、局限（读结论前必看）

1. **没有 dtc**：本机没有 `dtc`，也没有 Python `libfdt`。DTS 文本是本脚本按
   struct 块逐 token 还原的，**不是 dtc 的反编译结果**：
   - 属性的 `label:`、`#include` 结构不可恢复（只有节点路径）；
   - phandle 还原是启发式的：`&{/路径}` 可能把多 cell 属性的后续 cell 值一起吞进
     `< >` 里，看 `reg` / `interrupts` 这类多 cell 属性时以 `dtb-key-compare.json`
     或十六进制为准；
   - `/dts-v1/;` 头部与节点顺序按 struct 块原样输出，与源码书写顺序可能不同。
2. **FIT 的 totalsize 只有 4096**：本包的子镜像用**绝对 `data-position`** 追加在 FIT
   之后，所以"FIT 头 4 KiB + 数据区"不等于磁盘上文件大小；表中 `data-position` 是
   相对**文件开头**的偏移（`fit_probe.py` 直接按此截取并复算哈希，4 个哈希全部对上，
   说明这个理解正确）。
3. **尾部 16 字节 `FWx0` 段头未用官方工具解码**：字段语义（magic/crc/version/长度）
   是按 QWRT 签名包对照**推断**的，见 `package-check.txt` §4/§6。
4. **没有解 rootfs（squashfs）**：`/etc/openwrt_release`、Passwall 组件清单、
   `/lib/upgrade/platform.sh`、默认 LAN/WAN 配置等属于包内容分析，不在本目录取证范围；
   本目录只覆盖 FIT / DTB / metadata / 签名层。
5. **未上机**：所有结论都来自**静态字节**。CT 真机（电信版机器）本次未通电、未刷机；
   U-Boot 行为、2.5G 口在 U-Boot 阶段是否可用、reset 键是否真能进 recovery，
   均**未在本机复现**，文档里相应位置都标了"外部资料/未复现/未证实"。
6. **git 仓库是浅克隆**：`.git/shallow` 的 graft 根 = `edaeeb3`（Merge PR #34），
   看不到 PR #34 的父提交，故"PR #34 的 patch 内容"改用外部 PR diff 佐证（`pr34-check.txt` D 段）。

## 四、复现命令

```powershell
# 1) 解 FIT + 提取 DTB + 校验 hash + 读尾部 metadata
python 光猫-CT-HG5585F\分析\fit_probe.py scan `
  "光猫-CT-HG5585F\物料\固件\ponwrt-airoha-an7581-fiberhome_hg5585f-ct-squashfs-sysupgrade.itb" `
  "光猫-CT-HG5585F\分析\ct-fit.json" "光猫-CT-HG5585F\分析\ct-fit.txt" `
  "光猫-CT-HG5585F\分析\extracted\ct"

# 2) DTB → DTS 文本
python 光猫-CT-HG5585F\分析\fit_probe.py dtb `
  "光猫-CT-HG5585F\分析\extracted\ct\fdt-1.bin" "光猫-CT-HG5585F\分析\ct-dtb.dts"

# 3) 三份 DTB 关键字段对照
python 光猫-CT-HG5585F\分析\dtb-compare.py `
  "光猫-CT-HG5585F\分析\extracted\ct\fdt-1.bin" `
  "光猫-CT-HG5585F\分析\extracted\cu\fdt-1.bin" `
  "光猫-CT-HG5585F\分析\extracted\qwrt-ct\fdt-1.dtb"

# 4) CT/CU DTS diff
git diff --no-index --unified=3 光猫-CT-HG5585F\分析\ct-dtb.dts 光猫-CT-HG5585F\分析\cu-dtb.dts
```
