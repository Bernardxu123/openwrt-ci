# 维护与开发文档 — JDCloud RE-SS-01 固件

> 面向维护者/二次开发者。记录构建原理、核心修复、固化优化、诊断工具与修改方法。
> 用户向说明见 `README.md`，刷机步骤见 `FLASH_GUIDE.md`。
>
> 最后更新：2026-07-31（overcommit=1、rc.local 兜底策略、keep.d 保留 sysctl.conf 的坑）

---

## 1. 项目概览

| 项目 | 说明 |
|------|------|
| 设备 | JDCloud RE-SS-01（魔改亚瑟） |
| SoC | Qualcomm IPQ6010，4× Cortex-A53 @ 1.8GHz（设备树超频，OPP 864~1800MHz） |
| 内存 / 存储 | 1GB DDR4 / 128GB eMMC |
| 源码 | [LiBwrt/LibWrt](https://github.com/LiBwrt/LibWrt) `25.12-nss` 分支（ImmortalWrt 25.12 基础） |
| 内核 | 6.12 + NSS v11.4 硬件加速固件 |
| 构建 | GitHub Actions（`ubuntu-22.04`），推送到 `main` 分支触发 |

### 分支约定（2026-07-31 起仅保留单分支）

- 仅 `main` 一个分支，push 触发 CI 编译（见 `.github/workflows/build.yml` 的 `on.push.branches`）。
- 不再有 dev/main 双分支，已删除 `Merge dev to main` 同步步骤。
- 日常直接在 `main` 上改动，推送即触发编译。

### 仓库关键文件

```
.github/workflows/build.yml      主编译流水线
.github/workflows/diagnose.yml   快速 defconfig 诊断（手动触发，见 §6）
configs/jdcloud_re_ss01.config   目标 .config（软件包/内核选项声明）
libwrt.sh                        DIY 脚本（克隆包、patch、固化优化，见 §5）
files/                           直接注入固件的文件（如 OpenClash 首启脚本）
```

---

## 2. 核心发现：feeds 包被 defconfig 静默丢弃（最重要）

### 2.1 现象

`.config` 里明确声明 `CONFIG_PACKAGE_xxx=y` 的 feeds 软件包（htop、samba4、ttyd、
luci-app-openclash、luci-app-passwall、xray-core、sing-box、miniupnpd、filemanager 等），
编译后**全部没有进入固件**，需要刷机后手动 `opkg install` 补装。
而基础系统包（dropbear、firewall4、opkg、curl、dnsmasq-full）、内核模块（kmod-*）、
以及手动 `git clone` 进 `package/` 的包（lucky、mosdns）都正常。

### 2.2 根因

**OpenWrt 的一个隐蔽 quirk**：把一份手写的 `.config` 直接交给 `make defconfig` 时，
首次解析会把几乎所有 **feeds 可选包**重置为默认值 `n`（写成 `# CONFIG_PACKAGE_xxx is not set`）。

诊断已证实以下事实，可排除其它猜测：

- 这些包**都在包索引里**（`tmp/.packageinfo` 各有 1 条记录），不是扫描失败。
- 依赖**完全满足**，不是依赖冲突。
- 单独跑两次 `make defconfig` **无效**，feeds 包仍被重置。
- 但把 `CONFIG_PACKAGE_xxx=y` **追加到已解析的 `.config` 上再跑 defconfig，就能保持 `=y`**。

结论：首次 defconfig 处理手写 config 时，feeds 包的配置项在解析过程中被丢弃；
在已解析出的完整 config 基础上重新声明这些包，defconfig 才会正确保留。

### 2.3 修复方案（已应用于 build.yml）

`Download DL Package` 步骤改为三段式：

```bash
make defconfig                              # 第一次：解析基础配置（feeds 包会被重置）
cat "$GITHUB_WORKSPACE/$CONFIG_FILE" >> .config   # 重新追加原始配置，再次声明所有包
make defconfig                              # 第二次：基于完整配置定稿，feeds 包正确保留
```

配套改动：`Load Custom Configuration` 步骤把配置文件从 `mv` 改为 `cp`，
保留原始 `$CONFIG_FILE` 供第二次追加使用。

> ⚠️ 修改 `.config` 或调整构建流程时，**务必保留这个三段式**。若改回单次 defconfig，
> feeds 包会再次全部丢失。

### 2.4 排查过程中排除的误区

以下假设均被诊断否定，记录在此避免后人重复踩坑：

| 曾怀疑的原因 | 排除依据 |
|--------------|----------|
| clone 包污染包索引 | 临时禁用全部 clone 后，feeds 包仍被丢弃 |
| Go 工具链缺失（xray/sing-box） | htop/nano 等零依赖包同样被丢弃，与 Go 无关 |
| 依赖冲突 | `.packageinfo` 中包齐全，强制选择后 defconfig 能保持 |
| passwall master 分支不兼容 | 移除 passwall clone 后问题依旧 |

---

## 3. 软件包配置（configs/jdcloud_re_ss01.config）

声明目标设备、NSS、内核选项与全部软件包。关键分组：

- **NSS 硬件加速**：`kmod-qca-nss-drv*`、`kmod-qca-nss-ecm`、NSS v11.4 固件、SKB Recycler、WiFi offload。
- **代理**：OpenClash（Meta）、Passwall（Xray/SingBox）。Passwall 及其依赖
  （chinadns-ng、dns2socks、microsocks、ipt2socks 等）**直接用 25.12 feeds 自带版本**，
  不再从 master clone（见 §5 第 2b 节）。
- **实用工具**：Lucky、MosDNS、UPnP、ttyd、filemanager、Samba4、htop、coremark、openssh-sftp-server。
- **内核优化**：BBR + FQ、RPS/XPS、kmod-nft-tproxy、kmod-nf-socket、kmod-wireguard。

### 增删软件包的方法

1. 在 `configs/jdcloud_re_ss01.config` 增删 `CONFIG_PACKAGE_xxx=y`。
2. 若包不在 feeds 中（如 lucky），需在 `libwrt.sh` 第 2 节 `git clone` 进 `package/`。
3. 有依赖的包，建议把依赖也显式写进 `.config`，避免 defconfig 解析时遗漏。
4. 推送 `main` 后，先看 `diagnose.yml`（§6）确认目标包解析为 `=y`，再等完整编译。

---

## 4. 构建流程（build.yml）

```
初始化环境 → 合并磁盘 → 检出 → 克隆源码(LibWrt 25.12-nss)
→ 缓存工具链/ccache → 加载配置(cp .config + 跑 libwrt.sh)
→ 应用补丁 → 下载 DL（三段式 defconfig，见 §2.3）
→ defconfig 诊断（打印关键包状态）→ 编译
→ 校验关键包 → 整理文件 → 发布 Release
```

### 校验关键包步骤

- **硬失败条件**：固件镜像（`*sysupgrade.bin`）未产出、关键内核模块（kmod-nft-tproxy、
  kmod-nf-socket、kmod-wireguard、kmod-qca-nss-ecm）未打入固件。
- **警告（不阻断）**：用户空间包以 `.ipk` 文件存在性判断，缺失仅告警。
  （早期用 manifest 精确匹配会产生假阴性，已弃用。）

---

## 5. 固化优化清单（libwrt.sh）

`libwrt.sh` 在构建时生成注入固件的文件。各节说明：

| 节 | 内容 | 落点 |
|----|------|------|
| 1 | 移除官方冲突插件（athena-led） | — |
| 2 | 克隆 feeds 不含的包：Argon 主题、Lucky、MosDNS | `package/` |
| 2b | Passwall 改用 25.12 feeds 自带版（不再 clone master） | — |
| 3 | 修复克隆包 Makefile 的 luci.mk/golang 路径 | — |
| 4 | `feeds update/install -a` | — |
| 4b | patch 内核 config-6.12 启用 BBR/FQ/schedutil | `target/linux/generic/config-6.12` |
| 5 | 基础 sysctl（swappiness、tcp_fastopen、RPS、netdev、脏页、overcommit、ARP gc_thresh） | `files/etc/sysctl.d/99-optimize.conf` |
| 6 | 关键 sysctl（BBR+FQ、PPPoE、缓冲、conntrack、IPv6、TCP 低延迟、conntrack buckets） | `files/etc/sysctl.conf` |
| 7 | **rc.local 兜底**（BBR、conntrack max/buckets、overcommit、min_free、optmem、fin_timeout、syn_backlog、schedutil governor） | `files/etc/rc.local` |
| 8 | NSS 诊断脚本 `nss-status` | `files/usr/bin/nss-status` |
| 9 | Passwall/Xray REALITY 握手超时调优 | — |
| 10 | sysupgrade 备份清单（/etc/lucky/、/etc/mosdns/、/etc/openclash/） | `package/base-files/files/etc/sysupgrade.conf` |
| 11 | 定时清缓存 + WireGuard 看门狗 | `package/base-files/files/etc/init.d/custom_task` |
| 12 | 首屏 CPU 占用（用 LibWrt 自带） | — |
| 13 | 首屏温度显示（CPU+WiFi） | `package/emortal/autocore/files/tempinfo` |
| 14 | Argon 蓝紫配色 | uci-defaults `990_set_argon_primary` |
| 15 | SMP IRQ 亲和性（4 核绑核，nss_queue0→CPU3 等） | `target/.../etc/init.d/smp_affinity` |
| 16 | NSS 驱动启动优先级提前（START=88） | — |
| 17 | pbuf auto_scale off + schedutil（多路径搜索不 break + uci-defaults 兜底 + **rc.local 最终兜底**）+ pbuf 启动优先级 START=89（88drv < 89pbuf < 93绑核） | uci-defaults `991_set_schedutil` |
| 18 | conntrack hash buckets=max/2 | 追加 sysctl.conf |
| 19 | RPS/RFS + 缓冲深化 | 追加 sysctl.d |
| 20 | TCP 低延迟（tw_reuse、fin_timeout、syn_backlog） | 追加 sysctl.conf |
| 21 | 文件系统/内存回收（NAS 脏页、min_free_kbytes、overcommit=**1** 而非 2） | 追加 sysctl.d |
| 22 | ARP 表 + packet_steering=**0**（LibWrt 官方：与 NSS offload 冲突） | uci-defaults `992_set_packet_steering` |
| 23 | WiFi 2.4G 默认 HE40 带宽 | uci-defaults `993_set_wifi_he40` |
| 24 | 版本号可读化：DISTRIB_REVISION=R{日期}（toplevel.mk）+ LuCI 状态页时间戳（10_system.js） | `include/toplevel.mk` + feeds |
| 25 | miniupnpd 租约 7天→1天（`scripts/upnp/999-change-default-leaseduration.patch`，构建期拷入 feeds） | `feeds/packages/net/miniupnpd/patches/` |

> 注：`scripts/upnp/` 下的 patch 由 libwrt.sh §25 拷入 feeds 对应包目录，
> **不参与** build.yml 根目录 Apply Patches 循环（路径基准不同）。

### uci-defaults 首启脚本一览

位于 `package/base-files/files/etc/uci-defaults/`，首次启动执行一次后自动删除：

- `990_set_argon_primary`：Argon 主题配色
- `991_set_schedutil`：CPU 调度改 schedutil（兜底，覆盖 pbuf 的 performance 默认）
- `992_set_packet_steering`：packet_steering=0（LibWrt 官方与 NSS 冲突，跟随上游）
- `993_set_wifi_he40`：2.4G WiFi 设 HE40（仅设 htmode，不动 SSID/密码）

> 注：`files/etc/uci-defaults/991_openclash_init` 是 OpenClash 首启参数预置
> （sniffer、tcp-concurrent、ipv6、mixed stack），与上述 991 不同路径不同名，互不冲突。

---

## 6. 诊断工具（diagnose.yml）

排查"包没编进固件"类问题的利器，**无需等待 2 小时完整编译**。

- 触发：`workflow_dispatch`（手动），`gh workflow run diagnose.yml --ref main`。
- 行为：克隆源码 → 加载配置 → 跑 libwrt.sh → 执行三段式 defconfig → 上传 artifact 后结束。
- 产物（`gh run download -n defconfig-diagnose`）：
  - `diagnose.txt`：关键包解析后状态（`=y` / `is not set` / `ABSENT`）+ `.packageinfo` 索引检查。
  - `feeds_inventory.txt`：feeds 安装情况、包目录、关键包 Makefile 存在性。
  - `defconfig.log`：defconfig 输出。
  - `resolved.config`：defconfig 解析后的完整 `.config`。

### 常用定位手法

- 包状态是 `is not set`（非 ABSENT）→ 包在索引里但被重置，多半是 §2 的 defconfig quirk。
- 包状态是 `ABSENT` → 包不在索引，检查 feeds 是否安装、Makefile 是否存在。
- "强制选择测试"：defconfig 后追加 `CONFIG_PACKAGE_xxx=y` 再 defconfig，若保持 `=y`
  说明包可选、依赖满足，问题在首次解析丢弃（即 §2 根因）。

> 注意：`gh` CLI 默认可能指向其它仓库，操作本仓库务必加 `-R Bernardxu123/openwrt-ci`。
> CI 日志需整个 job 跑完才能拉取；诊断 artifact 则随诊断 workflow 结束即可下载。

---

## 7. 刷机与配置保留

- **升级务必勾选"保留设置"**（LuCI 刷机的 keep settings，或 `sysupgrade -c`）。
  保留设置会备份 `/etc/config/`（WiFi、网络、防火墙等）+ sysupgrade.conf/keep.d 清单。
- **OpenClash 配置自动保留**：OpenClash 安装时自带 `/lib/upgrade/keep.d/luci-app-openclash`
  （内容为 `/etc/openclash/`），保留设置升级会自动备份订阅/规则/geo 数据。
  `libwrt.sh` 第 10 节另在 sysupgrade.conf 加了 `/etc/openclash/` 作双保险。
- **⚠️ 关键坑：`/etc/sysctl.conf` 会被 keep.d 恢复，固件内容对"保留设置升级"不生效**。
  `/lib/upgrade/keep.d/base-files-essential` 清单包含 `/etc/sysctl.conf`，
  保留设置升级时旧文件（含用户手动修改）会被恢复，覆盖新固件里 libwrt.sh
  第 6/18/20 节写入的参数。因此：
  - 关键 sysctl 参数**必须在 `rc.local` 里 `sysctl -w` 兜底**（第 7 节），
    rc.local 不在 keep.d 清单中，每次升级都被新固件覆盖，是唯一保证生效的位置。
  - 若要手动修改设备参数，直接改设备上的 `/etc/sysctl.conf` 即可持久
    （保留设置升级也不会丢）。
  - `sysctl.d/` 不在保留清单，新固件版本每次升级都生效。
- **WiFi HE40**：已存于 `/etc/config/wireless`，保留设置升级即保留；
  uci-defaults 993 仅为"全新刷机不带配置"场景提供 HE40 默认值。
- 首次刷入新固件前，建议手动备份 `/etc/openclash/` 与 `/etc/config/` 各一份，万无一失。

---

## 8. 已知问题与注意事项

- **lan2 端口抖动**：dmesg 中 `nss-dp ... lan2: PHY Link up/down` 反复出现，
  多为网线/水晶头/对端网卡物理问题，非软件缺陷。不用该口可在 UCI 禁用。
- **CPU 超频**：1.8GHz 为设备树超频（OPP 上限），schedutil 调度不砍上限，
  负载时仍可达 1.8GHz，空闲降频省电。
- **BBRv3 不可用**：byJoey/Actions-bbr-v3 要求 Linux 7.x + GRUB + Debian，
  本设备（6.12 + U-Boot + OpenWrt）不满足；需等上游内核升至 6.13+。当前 BBRv1+FQ 足够。
- **overcommit 必须为 1，不能用 2**：clash/sing-box/xray 等 Go 程序虚拟地址空间
  可达 ~1.4GB，接近 1GB RAM + 463MB zram 上限，`overcommit=2` 下大块 mmap 会被拒，
  代理软件可能无法启动。
- **qca-nss-pbuf 会把 governor 写回 performance**：uci-defaults(S95done) 在
  qca-nss-pbuf 之前执行，991_set_schedutil 的 uci 段会被覆盖；
  由 rc.local 最后阶段（S99 之后）强制写 schedutil 保证生效。
- **MosDNS 默认禁用**：OpenClash 的 `nameserver-policy` 已内置 DNS 分流
  （国内直连 223.5.5.5/119.29.29.29，海外走 DoH 代理），无需再叠 MosDNS。
- **构建环境依赖外部脚本**：初始化步骤用 `is.gd/depends_ubuntu_2204` 装依赖，
  该链接偶发不可用会导致"初始化环境"步骤失败，重跑即可，与代码无关。

---

## 9. 安全提醒

- 仓库为 **public**。切勿把订阅 URL/token、dashboard 密钥、设备密码提交进仓库。
- 订阅配置仅存在于路由器 `/etc/openclash/` 与本地备份，不进 git。
- 本文档及仓库内不含任何敏感凭据；设备管理地址为 `192.168.31.1`（内网），凭据另行保管。

---

## 10. 参考来源

- 源码：[LiBwrt/LibWrt](https://github.com/LiBwrt/LibWrt)（25.12-nss）
- 借鉴：[ZqinKing/wrt_release](https://github.com/ZqinKing/wrt_release)、
  [breeze303/openwrt-ci](https://github.com/breeze303/openwrt-ci)、
  [VIKINGYFY/OpenWRT-CI](https://github.com/VIKINGYFY/OpenWRT-CI)
- Passwall：[xiaorouji/openwrt-passwall](https://github.com/xiaorouji/openwrt-passwall)
- MosDNS：[sbwml/luci-app-mosdns](https://github.com/sbwml/luci-app-mosdns)
