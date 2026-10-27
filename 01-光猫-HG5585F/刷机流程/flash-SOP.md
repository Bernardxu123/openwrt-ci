# 光猫刷机 SOP · FiberHome HG5585F（联通 CU）

> 制定日期 **2026-10-17** ｜ 目标：备份全部数据 → 刷 U-Boot → 刷 ponwrt → PON 注册 → 桥接给 LibWrt
> 状态：**物料已备齐并校验；root 获取方式已确定但未执行；文件传输方案未打通**

---

## 0. 结论速览

| 问题 | 答案 |
|---|---|
| ponwrt 能不能驱动这台光猫？ | **能**。PON 制式 = `EPON_10G`（10G/1G 非对称），驱动表里 `10G-EPON 10G/1G` 状态 **✅ 已实测** |
| stock2ubi 内核版本检查 | **5.4.55，正好匹配**（2026-10-17 实测 `/proc/sys/kernel/osrelease`），不会挡 |
| 唯一的卡点 | **没有 root**。telnet 是 `opuser`(uid 100)、`CapEff=0`、零 SUID |
| 解法 | **串口 getty**。`/proc/consoles` 显示 `ttyS0 -W-` → 串口有登录提示符，走标准 busybox login（读 `/etc/passwd`+`/etc/shadow`），**不是** telnetd 那套私有校验 |
| 需不需要拆机 | **要**（接 TTL 线），但**不需要拆到能操作芯片**，焊 3 根线即可 |
| 会不会断网 | 会。刷引导阶段光猫会重启重注册，**断网 1–3 分钟** |
| 建议先拿哪台试 | **CT 那台**（未注册、2.5G 口），练手不丢宽带 |

---

## 阶段 0 · 物料（✅ 已完成）

全部在 `downloads/`，含 sha256 见 `downloads/MANIFEST.md`。重拉用 `tools/fetch_flash_files.py`。

| 物料 | 说明 |
|---|---|
| `an7581-fiberhome-hg5585f-cu-firstblock.bin` | **推荐**：整块 128KB 写 NAND `0x0`（前 `0x800` 是 `0xFF` 擦除态，ATF 头在 `0x800`） |
| `an7581-fiberhome-hg5585f-cu-preloader.bin` | 备选：NAND `0x800` 写这个，前 0x800 保持擦灭。两者**等价** |
| `an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip` | BL31+U-Boot FIP |
| `an758x-stock2ubi` | aarch64-musl 静态 ELF，**在原厂系统里以 root 运行**，起 Web `:3333` 做备份+刷引导 |
| CT 三件套 | 同样下好了，试刀机用 |

> ⚠️ release 资产名用**连字符** `hg5585f-cu`；ponwrt profile 用**下划线** `fiberhome_hg5585f_cu`。下错机型=砖。

**还缺**：ponwrt 固件本身（`sysupgrade.itb`）。上游 `pbs05/ponwrt` **不发 release**，要用云编译
（`qwpianzhang/Actions-OpenWrt-HG5585F`，**必须把 `source` 切到 `pbs05/ponwrt`**，`profile=fiberhome_hg5585f-cu`）。
建议先跑一次 `scope=toolchain-only` 预热缓存再跑 `firmware`（免费 runner 6h 上限，全量大概率超时）。

---

## 阶段 1 · 硬件准备

- **3.3V USB-TTL 串口线**（⚠️ **不要接 VCC**，只接 `TXD`/`RXD`/`GND`；方向是 `TTL TX→猫 RX`、`TTL RX←猫 TX`）
- 波特率 **115200, 8N1**（`/proc/cmdline`: `console=ttyS0,115200n8`）
- 杜邦线若干，可能要**开机前先接好 GND**（有些板子 GND 不接对就不出字符）
- 建议先在 **CT 那台**上把整条流程走通

**判断串口通没通**：插上 TTL → 给光猫断电再上电 → 应该先看到 bootloader 输出，然后 Linux 的
`console=ttyS0` 启动日志，最后停在 `login:`。

---

## 阶段 2 · 拿 root（关键一步）

### 2.1 为什么 telnet 不行（已实测，别重试）

| 尝试 | 结果 |
|---|---|
| `/fhrom/bin/su_tool` | 无输出，仍 opuser |
| 往 `/var/tel_passwd`（`/tmp/tel_passwd`，telnetd 实际读的）加 root 行 | 拒。口令必须 `$5$fh$` SHA-256 crypt；复用 admin 那串哈希仍拒 |
| 同步改 `/etc/shadow`（`/tmp/shadow`）root 的 `$6$` SHA-512 | **telnetd 仍拒** → 它还有别的校验 |
| 全系统 SUID | **0 个** |

### 2.2 为什么串口可以

telnetd 是烽火私有实现；**串口 getty 是标准 busybox `login`**，只读 `/etc/passwd` + `/etc/shadow`。
而 `/etc/shadow` 是指向 `/tmp/shadow` 的符号链接，`/tmp` 是 **777 且无 sticky 位** →
`mv -f` 可以 `rename()` 整体替换（**这条已实测可行**，当时替换成功、只是 telnetd 不认）。

### 2.3 步骤

```powershell
# ① 开光猫访问通道（telnet 用）
#    长流程/不想被自动摘：--ttl 0（一直开启，手动 off）
python tools/ont.py on --ttl 7200

# ② 改 /tmp/shadow 里 root 的口令（自动备份 + 改完校验 + 打印前提条件）
python 光猫-HG5585F/tools/ont_setrootpw.py --set
python 光猫-HG5585F/tools/ont_setrootpw.py --status     # 只看状态

# ③ 接 TTL 线，串口终端里用 root / <你设的口令> 登录 getty
#    登录后先确认：
#       cat /proc/self/status | grep -i uid     # 期望 Uid: 0
#       id
```

> ⚠️ **`/tmp` 是 tmpfs，光猫一重启就恢复原值。**
> 「改口令 → 串口登录 → 跑 stock2ubi 完成备份+刷引导」必须**在同一次开机内**做完，中途别重启。

> 🔁 用完还原：`python 光猫-HG5585F/tools/ont_setrootpw.py --restore`
> （其实重启就自动还原了，这也是它比在 telnet 上长期留 root 口令干净的地方。）

### 2.4 恩山「su / 网页上传 fip」说法核实（2026-10-19 实测）

| 说法 | 核实结果 |
|---|---|
| telnet 登录后 `su`，密码 `Fh@`+MAC 后六位 | **本机 CU 固件不成立**：`su` 存在，但该密码及 `.81`–`.84` 派生 MAC、PON SN/设备 SN 变体全部 `incorrect password` |
| 改 `/etc/shadow` 或 `/var/tel_passwd` 就能 su | **不成立**：改这两个文件对 `su` 无效（改 root 哈希、加 root 行/明文均无效；未 strace 确认实际读取路径） |
| 工厂 CLI `generate rootkey` 可当 su 密码 | **未证实**：命令返回 success，但 key 不打印、`/fhconf/fh_key_conf` 为空 |
| 只登录 web 超管，在网页后台上传 `*-bl31-u-boot.fip` 就能进 U-Boot | **说法不完整**：那个网页是 `an758x-stock2ubi` 在 **`:3333`** 起的临时页，必须先 telnet `su` 到 root 再运行；原厂超管的「固件升级」页（`/fh_api/tmp/FHUPAPIS?action=upgradeimage`）从页面/接口看是 FiberHome 固件升级用途，不是 stock2ubi 的 fip 上传页（未实测裸 fip） |

**结论**：本机 CU 固件没有找到可用的 telnet→root 路径；恩山/mao.fan 的免拆流程（telnet → `su` → stock2ubi → `:3333` 上传 firstblock + fip）在 HG5382A/部分机型成立，但这台的 `su` 密码未知。**仍按 §2.2/2.3 的串口 getty 路线拿 root**；如果日后找到这台的 `su` 密码，可以直接走 stock2ubi，省掉串口。

---

## 阶段 3 · 备份（别跳过）

### 3.1 文件怎么送进光猫 —— ⚠️ **未打通**

原计划「PC → 路由器(192.168.1.2:8081) → 光猫 wget」**失败**：光猫 `wget` 能拿到连接但下载 0 字节
（ping 0.5ms 通、ARP REACHABLE，所以不是网络不通，而是服务侧问题或光猫侧有过滤）。
三个备选，按可行性排序：

| 方案 | 做法 | 评价 |
|---|---|---|
| **A 加路由（推荐）** | 拿到串口 root 后：`route add -net 192.168.31.0/24 gw 192.168.1.2`，然后 ONT 用 `/fhrom/bin/wget` 从 PC 的 HTTP 拉 | 有 root 后最干净，不用给光猫开放向 |
| B tftp | 路由器上起 tftpd，ONT `tftp 192.168.1.2` | 路由器 busybox 是否带 tftpd 待确认 |
| C telnet 文本传输 | PC 侧 `uuencode` → ONT 侧 `uudecode`（**两个都有**，已确认 `/usr/bin/uuencode`/`uudecode`） | 1MB 约 1.4MB 文本，笨但零依赖，现在就能做 |
| D USB | U 盘插光猫 USB 口 | 挂载通常也要 root |

**已知的坑**（省得重踩）：
- 光猫受限 shell 按**命令名**拉黑名单，**裸 `wget` 被拦**；要用绝对路径 **`/fhrom/bin/wget`**（真 GNU Wget 1.21.4）。`tftp`（BusyBox）不拦。
- 被拦清单：`dd` `rm` `cp` `ln` `head` `uname` `which` `id` `df` `wget`…；放行：`ls` `cat` `echo` `grep` `wc` **`mv`** `tar` `sed` `openssl` `/fhrom/bin/*`

### 3.2 stock2ubi 备份流程（读源码确认过）

```
串口 root shell 里：
    /tmp/an758x-stock2ubi            # 首次会检查 osrelease==5.4.55（本机满足）
    # 默认监听 3333，可用 --listen IP:PORT 改；--ignore-kernel-version 可跳版本检查
```

然后**在 PC 上**（通道已开的情况下，PC 能到 192.168.1.1，但 **3333 端口要在串口 root 起来后才通**）：

```
浏览器打开 http://192.168.1.1:3333/
  → 页面读 /proc/mtd 列出 17 个分区
  → 逐个点下载，文件名 mtd{index}-{name}.bin
```

**必须全部下完**，尤其是：

| 分区 | 内容 | 为什么 |
|---|---|---|
| **mtd13 `factory` (3 MiB)** | PON 身份 + **APONCAL 光模块校准** + **MT7916 WiFi EEPROM** | 缺 APONCAL → PON 起不来；缺 EEPROM → WiFi 起不来 |
| mtd0 `boot` | 原厂引导 | 回滚用 |
| mtd2/mtd6 `KernelA/B` | 双系统内核 | 回滚用 |
| mtd5/mtd9 `RootfsA/B` | 双系统 rootfs | 回滚用（当前跑的是 B 槽，`bootflag=1`） |

下载完存到 `光猫-HG5585F/backup/`（**PC 上，别只留在 /tmp**）。

---

## 阶段 4 · 刷 U-Boot

在 `http://192.168.1.1:3333/` 同一页面：

```
① 上传 an7581-fiberhome-hg5585f-cu-firstblock.bin
② 上传 an7581-fiberhome-hg5585f-cu-bl31-u-boot.fip
   （工具自动写引导并重启）
```

重启后按 README 的**手动路径**：
1. 上电约 1 秒内**按住 Reset** → 进 U-Boot Web recovery
2. 网线接上，`http://192.168.0.1/`（首次启动可能要等约 1 分钟）
3. 首次安装顺序：
   - **重建 UBI / Rebuild UBI**
   - 写入 `bl31-u-boot.fip`
   - **恢复板级数据卷** ← 把阶段 3 备份的 factory 写回去
   - 上传 ponwrt 的 `sysupgrade.itb`
   - **启动系统 / Boot system**

> 后续再升级直接用 **刷写系统 / Install system**。

---

## 阶段 5 · 刷 ponwrt（如果走完阶段 4 就已经带上了）

`sysupgrade.itb` 从云编译产物拿（见阶段 0）。

---

## 阶段 6 · PON 注册与桥接

```
LuCI → 网络 → PON → 配置

 PON line mode      epon-10g-1g       ← 10G/1G 非对称；EPON 下 serial_number/Registration-ID 隐藏
 EPON OAM:
   operator         ctc               ← 2026-10-19 实测：上海联通这台 OLT 必须 ctc
                                          ieee 能 MPCP 注册（LLID 有效）但 OAM 不认证 → service_ready=0
   loid             000000000000000014509791
   loid_password    留空
   ge_ports         4
```

> ✅ **2026-10-19 实测成功（ponwrt 直接做路由器）**：`br-lan=192.168.31.1`，LAN1-4 + WiFi 都在 `br-lan`；`pon0.995` 直接跑 PPPoE（`02105250448` / `052356`），WAN 拿到 `100.80.202.91`，ping `223.5.5.5` 6ms、DNS 正常。
> **关键坑**：OAM 选 `ieee` 时 PON 能注册但 `service_ready=0`、`pon0.995` 收不到包；改成 `ctc` 后 `service_ready=1`、PPPoE 立即认证成功。
> `pon-watchdog` 调试期先 `disable`——它的恢复动作曾尝试卸载 `airoha_xpon` 失败（`pon0.995/pond` 仍有引用），把 PON 栈留在半死状态。`pon` 与 `airoha-pond` 保持 enable。

身份写入：**网络 → PON → 配置 → PON board data**，上传
`mtd13 factory`（3MiB）经 `pbs05/fiberhome-factory` 转出的 **1 MiB** 镜像
（ponwrt 期望 `pon_data_target factory ubi 1048576`，差值就是转换的部分）。

`factory` 1MiB 布局与已备份的身份：

| 偏移 | 大小 | 内容 | 备份状态 |
|---|---|---|---|
| `0x000000` | 2KB | APONCAL 光模块校准 | ❌ **必须靠阶段 3 拿到** |
| `0x001000` | 4KB | MT7916 WiFi EEPROM | ❌ **必须靠阶段 3 拿到** |
| `0x002000` | 6B | Base MAC = `D0:69:FF:16:32:80` | ✅ 已知 |
| `0x002010` | 8B | PON SN = `FHTTC1C6ACAA` | ✅ 已知 |
| `0x002020` | 32B | 整机 SN = `01FFFFFFFF010FFF25D069FF16328037` | ✅ 已知 |

### 桥接给 LibWrt（可选，本次未采用）

> 2026-10-19 实际采用的是「ponwrt 直接做路由器」：`br-lan=192.168.31.1`，LAN1-4 + WiFi 都在 br-lan，`pon0.995` 直接跑 PPPoE；旧的 LibWrt 目前已不在 WAN 路径上。下面保留桥接方案供以后切换。

光猫 PON → 桥到 LAN 口。ponwrt **没有可视化的 GEM→桥配置**（`luci-app-pon` 只有线路/OAM/board data），
要手工按 `luci-app-iptv` 的做法建 `pon0.<VID>`（802.1q）再和物理口组 bridge。

你的业务是 **VLAN 995 已在光猫侧解标签**（见 `data/wan-connections.txt`），所以：
- 刷完后在 ponwrt 里新建一条 VLAN 995 的 bridge 接口，或
- 更简单：直接让 LibWrt 的 WAN 收**带 995 tag** 的流量，LibWrt 侧加 `.995` 子接口拨号
- PPPoE 账号不变（`02105250448` / `052356`），一直在 LibWrt 上

---

## 回滚

| 情况 | 恢复 |
|---|---|
| 刷引导失败 / 卡住 | 按住 Reset 进 U-Boot Web recovery，用阶段 3 的 `mtd0 boot` 备份刷回 |
| ponwrt 起不来 | 同上，回刷原厂 `boot` + `KernelA/B` + `RootfsA/B` |
| PON 注册不上 | 核对 LOID / PON SN / Base MAC 三样；仍不行就把 factory 原样写回 |
| 最坏：光猫彻底不动了 | TTL 串口进 bootloader（reset 键在新固件里是 GPIO35），手动写回原厂 BL2 |

---

## 风险清单

1. **⚠️ 千万别用 `huladabang/ponwrt` 那个 fork**（落后上游 10 天）。它缺 PR #21：
   **reset 键 DTS 指向 GPIO0，而 GPIO0 实际是 `uart1_txd` 没接到按键**，实测按键是 **GPIO35**。
   用它刷出来 **reset 键无效 → U-Boot HTTP recovery 进不去**，那是唯一的救命通道。
   云编译的 `source` 输入项**必须切到 `pbs05/ponwrt`**（那个仓库默认是 `qwe3017/ponwrt`）。
2. **CT 机型另有未合补丁**（PR #34，open）：GPY211C 2.5G 口 reset 时序竞态，热重启 `lan1` 会
   NO-CARRIER 到下次冷启动。修法是 DTS 写死 `ethernet-phy-id67c9.de10`。拿 CT 试刀时要留意。
3. **CT 是电信版**，插联通的纤能否注册取决于 PON 制式和 OLT 兼容性（波长都不一样）。
   它作为 ONT 上线还需要联通给它**新 SN/LOID 入网**——**不要克隆现有 CU 的 SN**（那是冒用设备身份）。
4. **无线 NPU 卸载没生效**（上游 issue #16 至今 open：MT7916 走 mt7915e，Airoha NPU 的 MT76 构建开关
   只在 mt7996e 路径下）。别指望刷完 WiFi 能跑满硬件卸载。
5. 你的主路由 IPQ60xx **全是千兆口**，CT 的 2.5G 口端到端暂时吃不到收益。
6. 光猫通常是运营商租赁设备，刷第三方固件可能违反租赁协议/服务条款——你自己判断。

---

## 待办清单

- [ ] 买 3.3V USB-TTL 线（**不接 VCC**）
- [ ] 云编译 ponwrt（`source=pbs05/ponwrt`，`profile=fiberhome_hg5585f-cu`）
- [ ] 打通「文件送进光猫」（阶段 3.1，建议先试方案 C 的 uuencode，零依赖）
- [ ] 阶段 2 改 root 口令 → 串口登录验证（**建议先在 CT 上试**）
- [ ] 全分区备份到 `光猫-HG5585F/backup/`
- [ ] 刷 U-Boot → 恢复板级数据卷 → 刷 ponwrt
- [ ] PON 注册 + 桥接 + LibWrt 侧 PPPoE 回归

---

## 工具（都在 `光猫-HG5585F/tools/`）

| 文件 | 用途 | 状态 |
|---|---|---|
| `fetch_flash_files.py` | 下载 + 校验刷机物料（带重试，家宽到 GitHub 会抖） | ✅ 已用 |
| `ont_setrootpw.py` | 改 / 还原 `/tmp/shadow` 的 root 口令，为串口登录铺路 | ⚠️ `--status` 已验证；`--set` **未执行** |
| `ont_push_file.py` | PC→路由器→光猫 传文件 | ❌ **失败且有副作用，别用**（见下） |
| `ont.py` / `ont.bat` | 访问通道开关 | ✅ |
| `ont_shell.py` | Telnet 多命令会话 | ✅ |
| `fhtool_probe.py` | `/fh_tool/api` 只读采集 | ✅ |
| `fhtool_telnet.py` | 开 Telnet + 验握手 | ✅ |

> 🔴 **`ont_push_file.py` 已知副作用**：里面用 `killall uhttpd` 腾端口，而**路由器只有一个 uhttpd 实例**
> （LuCI 就靠它），会被一起杀掉 → 路由器 LuCI 网页打不开。恢复：`/etc/init.d/uhttpd restart`。
> 这个脚本在验证失败后应标注废弃或改成 `-p` 追加端口而非 killall。