# 优化留档（OPTIMIZATION LOG）

> 本文件记录 openwrt-ci 仓库历次优化的动机、内容与结果，供后续维护与讨论参考。
> 最后更新：2026-08-04

---

## 1. 优化时间线

| Commit | 日期 | 内容 | 结果 |
|--------|------|------|------|
| `2afec3d` | 07-31 | WiFi 2.4G HE40 + sysupgrade 备份 OpenClash 配置 | ✅ 已刷机验证 |
| `6bb7e17` | 07-31 | rc.local 全面兜底 sysctl + overcommit=1 + pbuf schedutil 修复；单分支化（删 dev） | ✅ 已刷机验证 |
| `37d5d64` | 07-31 | 清理遗留文件（legacy/、preset 脚本、含密码 ssh 脚本、临时 json） | ✅ |
| `8ed0b4e` | 07-31 | 借鉴 4 库 7 项优化（见 §2） | ❌ 构建失败 → 见 §3 踩坑 |
| `039256e` | 08-03 | CI pin 回归修复（temp-reserve-mb、delete-older-releases v0.3.4） | ❌ 构建仍失败 → 见 §3 踩坑 |
| 本次 | 08-04 | 移除 maximize-build-space 步骤（runner 镜像不兼容） | 🔄 构建中 |

---

## 2. 8ed0b4e 七项优化明细

对**路由器运行时**有效的（进固件，刷机后生效）：

| # | 内容 | 来源 | 落点 |
|---|------|------|------|
| 1 | **NSS SQM 引擎** kmod-qca-nss-drv-qdisc（sqm-scripts-nss 的运行时依赖，LibWrt target.mk 默认包，显式声明防 defconfig 丢弃） | 分析发现缺失 | `configs/jdcloud_re_ss01.config` |
| 2 | **packet_steering=0**：LibWrt 自带 992_set-network.sh 明确"与 NSS 冲突"主动关，之前我们设 1 方向反了 | LibWrt 源码 | libwrt.sh §22 |
| 3 | **版本号可读化**：DISTRIB_REVISION=R{日期}（sed include/toplevel.mk REVISION 定义）+ LuCI 10_system.js 编译时间戳 | breeze303 + VIKINGYFY | libwrt.sh §24 |
| 4 | **UPnP 租约 7天→1天**（0 值改 8h），防 conntrack 被家用设备租约撑大 | ZqinKing | `scripts/upnp/999-change-default-leaseduration.patch` + libwrt.sh §25 |
| 5 | **pbuf 启动顺序** START 95→89（88drv < 89pbuf < 93绑核，内存先于绑核就绪） | ZqinKing | libwrt.sh §17 追加 |

只对**编译流程**有效的（不影响路由器运行）：

| # | 内容 | 落点 |
|---|------|------|
| 6 | concurrency（同分支重复 push 取消旧跑）+ actions pin 版本 | `build.yml` |
| 7 | Packages.tar.gz 全量 ipk 打包随 Release 发布（补装包免重编） | `build.yml` Organize Files |

> ⚠️ §24 版本注入曾依赖 `package/feeds/nss_packages/qca-nss-pbuf` 路径——实测 pbuf 包在
> `package/kernel/mac80211/files/`（nss-packages feed 无 qca-nss-pbuf），已修正。
> 另：`scripts/upnp/` 下 patch 不参与根目录 Apply Patches 循环（路径基准不同），由 libwrt.sh §25 用
> `install -Dm644` 拷入 feeds（feeds 的 patches 目录默认不存在，必须 install 创建）。

---

## 3. CI 踩坑记录（重要教训）

### 坑 1：maximize-build-space 与 GitHub runner 镜像不兼容
- `@v1`：不支持 `temp-reserve-mb` 输入（v1 action.yml 只有 7 个输入）→ "Unexpected input(s)" exit 32
- 删除该输入后：v1 脚本硬编码 `sudo umount /mnt`，而 **2026 年新版 runner 镜像已移除 /mnt 临时盘**
  （单块 146G 大盘，113G 可用）→ `umount: /mnt: not mounted` exit 32（脚本 set -e）
- **结论**：新版镜像空间充足（OpenWrt 编译仅需 ~20G），该 action 已无存在必要 → 直接移除步骤。
  这是 2026 runner 镜像变化对旧 action 的兼容性问题，任何外部 action 都可能踩。

### 坑 2：pin actions 版本的正确姿势
- `dev-drprasad/delete-older-releases` 只有 v0.x tag（最新 v0.3.4），**没有 v1**，pin `@v1` 会 404
- **验证方法**：`gh api repos/{owner}/{repo}/git/ref/tags/{tag}` 确认 ref 存在 + 拉 action.yml 核对输入参数
- pin 原则：先验证 ref 存在 → 再核对 `inputs` 与用法匹配 → 最后才写进 workflow

### 坑 3：其他已确认 pin 版本
- `actions/checkout@v4` ✅、`ncipollo/release-action@v1` ✅、`Mattraks/delete-workflow-runs@v2` ✅
- `HiGarfield/cachewrtbuild` 无 tag（仅 main），保持 @main
- actions 版本验证脚本见 §5 附件

---

## 4. 对路由器有效的运行时优化（固件外，刷机后操作）

- **SQM 配置**：qdisc 引擎已进固件，LuCI → QoS 里配置 NSS 队列（上海联通 bufferbloat）
- **5G 降功率**：27dBm → 25dBm（信道共享环境实测干扰大）
- **WPA3**：当前 WPA2
- **申请公网 IPv4**：打 10010 申请动态公网 IP；否则 Lucky DDNS 必须走 IPv6（CGNAT 下 v4 是伪地址）

---

## 5. 后续优化建议（待讨论，未实施）

| # | 建议 | 收益 | 权衡 |
|---|------|------|------|
| 1 | **DL 缓存**：cachewrtbuild 已支持 extra_directories，把 dl/ 加入缓存 | make download 从 10-20min 降到 ~1min | GitHub 仓库级缓存上限 10GB，可能挤掉 toolchain 缓存导致白编 |
| 2 | **pin 上游 commit**：REPO_COMMIT 钉到已验证 hash（当前 b6364cb） | 上游改坏代码不砸自用构建 | 失去自动跟随修复；mixkey 需带 commit |
| 3 | **周自动构建**（schedule）：配合 #2 每周检验上游 | 定期评估上游变化 | 无 |
| 4 | **NSS 裁剪**：target.mk 默认 19 个 NSS 驱动（eogremgr/gre/map-t/match/mirror/tun6rd/tunipip6/vxlanmgr/macsec）删一半 | 固件省 5-10MB | 改上游 target.mk，需幂等 sed 防 patch 冲突 |
| 5 | **失败通知**（Server酱/Telegram） | 自动构建场景有用 | push 触发意义小 |
| 6 | **验证增强**：Verify packages 补 kmod-qca-nss-drv-qdisc 检查 | 防回归 | 无 |
| 7 | Ubuntu 22.04→24.04 | — | ⚠️ 不建议：is.gd depends_ubuntu_2204 只支持 22.04 |

---

## 6. 参考仓库借鉴结论

| 仓库 | 借鉴点 | 结论 |
|------|--------|------|
| LibWrt（上游源码） | packet_steering 冲突、schedutil 默认、target.mk NSS 全家桶、keep.d 坑 | 已吸收 |
| ZqinKing/wrt_release | UPnP 租约、pbuf START、passwall 超时、sysupgrade 备份、绑核思路 | 已吸收（绑核以我们实测 /proc/interrupts 数据为准） |
| VIKINGYFY/OpenWRT-CI | 10_system.js 时间戳、清理链 | 已吸收（清理链我们本就有） |
| breeze303/openwrt-ci | 版本号注入、ipk 打包、011 MBO patch | 已吸收 |

未采纳：NSS 固件 11.4 保持（官方推荐稳定版，mesh/WDS 需要）；cachewrtbuild 缓存方案已最优；
conntrack/BBR/overcommit 兜底比 3 家都强（rc.local 是 sysupgrade 保留设置下唯一可靠兜底）。

---

## 7. 附件：actions ref 验证脚本

```powershell
$refs = @(
  @{r="easimon/maximize-build-space"; t="v1"},
  @{r="actions/checkout"; t="v4"},
  @{r="ncipollo/release-action"; t="v1"},
  @{r="Mattraks/delete-workflow-runs"; t="v2"},
  @{r="dev-drprasad/delete-older-releases"; t="v0.3.4"}
)
foreach ($x in $refs) {
  $ok = gh api "repos/$($x.r)/git/ref/tags/$($x.t)" --jq '.ref' 2>$null
  if ($ok) { "OK  $($x.r)@$($x.t)" } else { "MISS $($x.r)@$($x.t)" }
}
```

---

## 8. 2026-08-14 深度分析批次(本地未提交,待 review + push)

来源:对运行固件(07-27 构建,已滞后)做 6 轮只读 SSH 审计 + 4 路调研(LiBwrt 上游/breeze303/ZqinKing/laipeng668/VIKINGYFY/社区)。审计结论:运行固件为 07-27 构建,8-13 已有 R20260813-1712/R20260813-1119 两个成功 Release 未刷;`/etc/rc.local` 实测在 keep.d/base-files-essential 保留清单内(与 §7 文档记载相反),保留设置升级会覆盖新固件兜底,升级前需先 `mv /etc/rc.local /root/rc.local.old`;上游 08-01 已合入 JDCloud 升级 emmc.sh 迁移(6418a73),下次升级跨新路径,建议备 factory.bin。

本批次改动(全部未提交):

| # | 内容 | 落点 | 说明 |
|---|------|------|------|
| 1 | NSS 固件 11.4→12.5(测试轮) | `configs/jdcloud_re_ss01.config` | 12.x 不支持 802.11s mesh,家用可用;如要 mesh 回退 11.4。push 前可用 diagnose.yml 验证 12_5 符号 |
| 2 | `nf_conntrack_acct=0` | libwrt.sh §26 | LibWrt 默认 1(每包记账),软件路径省 CPU |
| 3 | ECM `accel_delay_pkts=5` | libwrt.sh §7 rc.local | qca-nss-ecm.init 硬编码 1(QSDK 默认 5),PPPoE 短连接去抖 |
| 4 | dnsmasq `cachesize=2048` | libwrt.sh §27 uci-defaults 994 | 默认 150;DNS 链 dnsmasq→OpenClash(7874) |
| 5 | `CONFIG_KERNEL_SKB_RECYCLER_PREALLOC=y` | configs | SKB 池启动预分配,突发流量减少分配延迟 |
| 6 | ksmbd 内核态 SMB | configs (`kmod-fs-ksmbd` + `ksmbd-tools`) | LuCI 可切后端,NAS 吞吐/CPU 更优(A53);需实测对比 samba4 |

未采纳:周自动构建(schedule)——保持手动触发(workflow_dispatch),需要时再编译。

审计中确认无问题的项(勿重复做):packet_steering=0 + RPS 实测全 0(无 set-irq-affinity 冲突)、`nf_conntrack_tcp_no_window_check=1` 生效、threaded-NAPI 已硬编码启用、BBR+FQ 生效、lan2 抖动为电视机百兆口开关机所致(正常,不禁用)。
