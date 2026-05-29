#!/bin/bash

# ============================================
# OpenWrt DIY 脚本 - JDCloud RE-SS-01 专用
# 基于 LiBwrt/openwrt-6.x main-nss 分支
# 包含 OpenClash 依赖设置
# ============================================

# 移除要替换的包 (避免与自定义版本冲突)
rm -rf feeds/packages/net/mosdns
rm -rf feeds/packages/net/msd_lite
rm -rf feeds/packages/net/smartdns
rm -rf feeds/luci/themes/luci-theme-argon
rm -rf feeds/luci/themes/luci-theme-netgear
rm -rf feeds/luci/applications/luci-app-mosdns
rm -rf feeds/luci/applications/luci-app-netdata
rm -rf feeds/luci/applications/luci-app-serverchan

# ============================================
# Git稀疏克隆函数
# ============================================
function git_sparse_clone() {
  branch="$1" repourl="$2" && shift 2
  git clone --depth=1 -b $branch --single-branch --filter=blob:none --sparse $repourl
  repodir=$(echo $repourl | awk -F '/' '{print $(NF)}')
  cd $repodir && git sparse-checkout set $@
  mv -f $@ ../package
  cd .. && rm -rf $repodir
}

# ============================================
# 1. 禁用掉官方可能会拉取的冲突插件
# ============================================
rm -rf package/emortal/luci-app-athena-led

# ============================================
# 2. 添加额外插件 (feeds 中不包含的)
# ============================================

# Argon 主题及配置
git clone --depth=1 https://github.com/jerrykuku/luci-theme-argon package/luci-theme-argon
git clone --depth=1 https://github.com/jerrykuku/luci-app-argon-config package/luci-app-argon-config

# Lucky (DDNS/端口转发/STUN) - 不在 immortalwrt feeds 中
git clone --depth=1 https://github.com/sirpdboy/luci-app-lucky package/lucky-src
cp -rf package/lucky-src/luci-app-lucky package/luci-app-lucky
cp -rf package/lucky-src/lucky package/lucky
rm -rf package/lucky-src

# MosDNS (使用 sbwml 版本，更稳定且功能完整)
git clone --depth=1 https://github.com/sbwml/luci-app-mosdns package/luci-app-mosdns

# ============================================
# 3. 修复 Makefile 路径
# ============================================
find package/*/ -maxdepth 2 -path "*/Makefile" | xargs -i sed -i 's/..\/..\/luci.mk/$(TOPDIR)\/feeds\/luci\/luci.mk/g' {}
find package/*/ -maxdepth 2 -path "*/Makefile" | xargs -i sed -i 's/..\/..\/lang\/golang\/golang-package.mk/$(TOPDIR)\/feeds\/packages\/lang\/golang\/golang-package.mk/g' {}
find package/*/ -maxdepth 2 -path "*/Makefile" | xargs -i sed -i 's/PKG_SOURCE_URL:=@GHREPO/PKG_SOURCE_URL:=https:\/\/github.com/g' {}
find package/*/ -maxdepth 2 -path "*/Makefile" | xargs -i sed -i 's/PKG_SOURCE_URL:=@GHCODELOAD/PKG_SOURCE_URL:=https:\/\/codeload.github.com/g' {}

# 取消主题默认设置
find package/luci-theme-*/* -type f -name '*luci-theme-*' -print -exec sed -i '/set luci.main.mediaurlbase/d' {} \;

# ============================================
# 4. 更新并安装 Feeds
# ============================================
./scripts/feeds update -a
./scripts/feeds install -a

# ============================================
# 4b. Patch 内核配置 — 启用 BBR + FQ
#     LiBwrt generic/config-6.12 明确禁用了 BBR 和 FQ
#     必须直接修改内核配置文件才能生效
#     (workflow 中 echo >> .config 无效，.config 优先级低于 config-6.12)
# ============================================
KERNEL_CONFIG="target/linux/generic/config-6.12"
if [ -f "$KERNEL_CONFIG" ]; then
  # 启用 BBR
  sed -i 's/^# CONFIG_TCP_CONG_BBR is not set$/CONFIG_TCP_CONG_BBR=y/' "$KERNEL_CONFIG"
  # 启用 FQ
  sed -i 's/^# CONFIG_NET_SCH_FQ is not set$/CONFIG_NET_SCH_FQ=y/' "$KERNEL_CONFIG"
  echo ">>> 内核配置已 Patch: BBR + FQ 启用 (默认拥塞控制由 sysctl 运行时设置)"
fi

# ============================================
# 5. 预置基础 sysctl 参数 (sysctl.d 目录)
# ============================================
mkdir -p files/etc/sysctl.d
cat > files/etc/sysctl.d/99-optimize.conf <<EOF
# 内存：优先使用物理内存，减少 zram 压缩开销
vm.swappiness=10
# TCP Fast Open (客户端+服务端模式)
net.ipv4.tcp_fastopen=3
# TCP 空闲连接不重置慢启动
net.ipv4.tcp_slow_start_after_idle=0
EOF

# ============================================
# 6. 追加关键参数到 /etc/sysctl.conf 末尾
#    sysctl.conf 在 sysctl.d/* 之后加载，确保不被覆盖
# ============================================
cat >> files/etc/sysctl.conf <<EOF

# === BBR 拥塞控制 (对 OpenClash 代理流量生效，不影响 NSS 硬件加速) ===
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr

# === PPPoE 优化 ===
net.ipv4.tcp_mtu_probing=1

# === 网络缓冲区 ===
net.core.rmem_max=16777216
net.core.wmem_max=16777216
net.ipv4.tcp_rmem=4096 87380 16777216
net.ipv4.tcp_wmem=4096 65536 16777216

# === 连接跟踪 ===
net.netfilter.nf_conntrack_max=163840
EOF

# ============================================
# 7. rc.local 兜底保障
#    启动最后阶段加载 BBR 模块 + 强制执行关键参数
#    (覆盖启动过程中任何其他脚本的修改)
# ============================================
cat > files/etc/rc.local <<'RCEOF'
# 加载 BBR 模块 (如果内核编译为模块)
modprobe tcp_bbr 2>/dev/null

# 兜底：确保关键 sysctl 参数生效
sysctl -w net.core.default_qdisc=fq >/dev/null 2>&1
sysctl -w net.ipv4.tcp_congestion_control=bbr >/dev/null 2>&1
sysctl -w net.ipv4.tcp_mtu_probing=1 >/dev/null 2>&1
sysctl -w net.ipv4.tcp_fastopen=3 >/dev/null 2>&1
sysctl -w net.ipv4.tcp_slow_start_after_idle=0 >/dev/null 2>&1

exit 0
RCEOF

# ============================================
# 8. 预置 NSS 硬件加速诊断脚本
# ============================================
mkdir -p files/usr/bin
cat > files/usr/bin/nss-status <<'NSSEOF'
#!/bin/sh
echo "========== NSS 驱动状态 =========="
cat /sys/kernel/debug/qca-nss-drv/stats 2>/dev/null || echo "  NSS debugfs 不可用"
echo ""
echo "========== ECM 前端加速状态 =========="
[ -d /sys/kernel/debug/ecm/ecm_db ] && {
  echo "  ECM 连接总数: $(cat /sys/kernel/debug/ecm/ecm_db/connection_count 2>/dev/null || echo 'N/A')"
} || echo "  ECM debugfs 不可用"
echo ""
echo "========== 连接跟踪 =========="
echo "  当前: $(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null || echo 'N/A')"
echo "  上限: $(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null || echo 'N/A')"
echo ""
echo "========== PPPoE NSS 卸载 =========="
dmesg | grep -i "pppoe.*nss\|nss.*pppoe" | tail -3 2>/dev/null || echo "  无可读日志"
NSSEOF
chmod +x files/usr/bin/nss-status

# ============================================
# 9. Passwall 连接超时调优
#    放宽 Xray REALITY 握手超时 + 增加采样次数
#    来源: ZqinKing/wrt_release
# ============================================
PASSWALL_UTIL="feeds/luci/applications/luci-app-passwall/luasrc/passwall/util_xray.lua"
if [ -f "$PASSWALL_UTIL" ]; then
  sed -i 's/maxRTT = "1s"/maxRTT = "2s"/g' "$PASSWALL_UTIL"
  sed -i 's/sampling = 3/sampling = 5/g' "$PASSWALL_UTIL"
  echo ">>> Passwall 超时参数已调优 (maxRTT=2s, sampling=5)"
fi

# ============================================
# 10. sysupgrade 备份配置
#     升级时自动备份这些配置目录
#     来源: ZqinKing/wrt_release
# ============================================
mkdir -p package/base-files/files/etc
cat > package/base-files/files/etc/sysupgrade.conf <<'EOF'
/etc/lucky/
/etc/mosdns/
EOF

# ============================================
# 11. 定时清理 + WireGuard 看门狗
#     每天凌晨 3:15 清理内核缓存
#     WireGuard 接口存在时自动添加保活 cron
#     来源: ZqinKing/wrt_release
# ============================================
mkdir -p package/base-files/files/etc/init.d
cat > package/base-files/files/etc/init.d/custom_task <<'EOF'
#!/bin/sh /etc/rc.common
START=99

boot() {
    sed -i '/drop_caches/d' /etc/crontabs/root
    echo "15 3 * * * sync && echo 3 > /proc/sys/vm/drop_caches" >> /etc/crontabs/root

    sed -i '/wireguard_watchdog/d' /etc/crontabs/root

    local wg_ifname=$(wg show | awk '/interface/ {print $2}')

    if [ -n "$wg_ifname" ]; then
        echo "*/15 * * * * /usr/bin/wireguard_watchdog" >> /etc/crontabs/root
        uci set system.@system[0].cronloglevel='9'
        uci commit system
        /etc/init.d/cron restart
    fi

    crontab /etc/crontabs/root
}
EOF
chmod +x package/base-files/files/etc/init.d/custom_task

# ============================================
# 12. 首屏美化 — cpuusage (LuCI 状态栏)
#     显示: CPU占用% + NSS硬件引擎负载 + ECM连接数
#     来源: ZqinKing/wrt_release
# ============================================
QUALCOMMAX_DIR="target/linux/qualcommax"
if [ -d "$QUALCOMMAX_DIR" ]; then
  mkdir -p "$QUALCOMMAX_DIR/base-files/sbin"
  cat > "$QUALCOMMAX_DIR/base-files/sbin/cpuusage" <<'EOF'
#!/bin/sh
cpu_usage=$(top -bn1 | head -n2 | awk -F'[ %]+' 'NR==2{print $2}')
combined_output=""

if [ -e "/sys/kernel/debug/qca-nss-drv/stats/cpu_load_ubi" ]; then
    nss_avg_utilization=$(awk 'NR==6 {print $2}' /sys/kernel/debug/qca-nss-drv/stats/cpu_load_ubi)
    combined_output="${combined_output}${nss_avg_utilization}"
fi

if [ -r "/sys/kernel/debug/ecm/ecm_db/connection_count_simple" ]; then
    connection_count=$(cat /sys/kernel/debug/ecm/ecm_db/connection_count_simple)
    echo -n "CPU: ${cpu_usage}% HWE: ${combined_output} ECM: ${connection_count}"
elif [ -n "$combined_output" ]; then
    echo -n "CPU: ${cpu_usage}% HWE: ${combined_output}"
else
    echo -n "CPU: ${cpu_usage}%"
fi
EOF
  chmod +x "$QUALCOMMAX_DIR/base-files/sbin/cpuusage"

  # Hook LuCI rpc 调用 cpuusage 而非默认 top
  LUCI_RPC="feeds/luci/modules/luci-base/root/usr/share/rpcd/ucode/luci"
  if [ -f "$LUCI_RPC" ]; then
    sed -i "s#const fd = popen('top -n1 | awk \\\'/^CPU/ {printf(\"%d%\", 100 - \$8)}\\\'')#const cpuUsageCommand = access('/sbin/cpuusage') ? '/sbin/cpuusage' : 'top -n1 | awk \\\'/^CPU/ {printf(\"%d%\", 100 - \$8)}\\\''#g" "$LUCI_RPC"
    sed -i '/cpuUsageCommand/a \\t\t\tconst fd = popen(cpuUsageCommand);' "$LUCI_RPC"
  fi
fi

# ============================================
# 13. 首屏美化 — tempinfo (温度显示)
#     显示: CPU温度 + WiFi温度
#     来源: ZqinKing/wrt_release
# ============================================
TEMPINFO_PATH="package/emortal/autocore/files/tempinfo"
mkdir -p "$(dirname "$TEMPINFO_PATH")"
cat > "$TEMPINFO_PATH" <<'EOF'
#!/bin/sh

IEEE_PATH="/sys/class/ieee80211"
THERMAL_PATH="/sys/class/thermal"

if grep -Eq "ipq40xx|ipq806x" "/etc/openwrt_release"; then
	wifi_temp="$(awk '{printf("%.1f°C ", $0 / 1000)}' "$IEEE_PATH"/phy*/device/hwmon/hwmon*/temp1_input 2>"/dev/null" | awk '$1=$1')"
else
	wifi_temp="$(cat "$IEEE_PATH"/phy*/hwmon*/temp1_input 2>"/dev/null" | awk '{printf("%.1f°C ", $0 / 1000)}' | awk '$1=$1')"
fi

if grep -q "ipq40xx" "/etc/openwrt_release"; then
	if [ -e "$IEEE_PATH/phy0/hwmon0/temp1_input" ]; then
		mt76_temp="$(awk -F ': ' '{print $2}' "$IEEE_PATH/phy0/hwmon0/temp1_input" 2>/dev/null")°C"
	fi
	[ -z "$mt76_temp" ] || wifi_temp="${wifi_temp:+$wifi_temp }$mt76_temp"
else
	cpu_temp="$(awk '{printf("%.1f°C", $0 / 1000)}' "$THERMAL_PATH/thermal_zone0/temp" 2>/dev/null")"
fi

if [ -n "$cpu_temp" ] && [ -z "$wifi_temp" ]; then
	echo -n "CPU: $cpu_temp"
elif [ -z "$cpu_temp" ] && [ -n "$wifi_temp" ]; then
	echo -n "WiFi: $wifi_temp"
elif [ -n "$cpu_temp" ] && [ -n "$wifi_temp" ]; then
	echo -n "CPU: $cpu_temp, WiFi: $wifi_temp"
else
	echo -n "No temperature info"
fi
EOF

# ============================================
# 14. 首屏美化 — Argon 主题蓝紫配色
#     primary=#6A89CC, transparency=0.3
#     来源: ZqinKing/wrt_release
# ============================================
mkdir -p package/base-files/files/etc/uci-defaults
cat > package/base-files/files/etc/uci-defaults/990_set_argon_primary <<'EOF'
#!/bin/sh

if [ ! -f /etc/config/argon ]; then
    touch /etc/config/argon
    uci add argon global
fi

uci set argon.@global[0].primary='#6A89CC'
uci set argon.@global[0].transparency='0.3'
uci commit argon
EOF
chmod +x package/base-files/files/etc/uci-defaults/990_set_argon_primary

# ============================================
# 15. SMP IRQ Affinity — 4 核 CPU 中断亲和性
#     RX/TX/NSS/EDMA 中断分配到不同核心
#     来源: ZqinKing/wrt_release
# ============================================
QUALCOMMAX_DIR="target/linux/qualcommax"
if [ -d "$QUALCOMMAX_DIR" ]; then
  mkdir -p "$QUALCOMMAX_DIR/base-files/etc/init.d"
  cat > "$QUALCOMMAX_DIR/base-files/etc/init.d/smp_affinity" <<'SMPEOF'
#!/bin/sh /etc/rc.common

START=93

PROG=smp_affinity

log_msg() {
    local irq_name="$1" affinity="$2" irq="$3"
    msg="$(printf "Pinning IRQ($irq) %-24s to CPU ${affinity}\n" "$irq_name")"
    logger -t "$PROG" "$msg"
}

cpus_to_bitmask() {
    local bitmask=0
    for range in ${*//,/ }; do
        start="${range%-*}"
        end="${range#*-}"
        if [ -z "$end" ]; then
            bitmask="$((bitmask | 1 << start))"
        else
            bitmask="$((bitmask | ((1 << (end - start + 1)) - 1) << start))"
        fi
    done
    printf '%x' $bitmask
}

set_affinity() {
    local irq_name="$1" affinity="$2" occurrence="${3:-1}" bitmask irq
    awk -v irq_name="$1" -v occurrence="$occurrence" '
        BEGIN{count=0}
        $NF==irq_name {
            if(++count==occurrence){
                sub(/:$/,"",$1)
                print $1
            }
        }' /proc/interrupts | while read -r irq; do
        $enable_log && {
            log_msg "$irq_name" "$affinity" "$irq"
        }
        bitmask=$(cpus_to_bitmask "$affinity") && echo "$bitmask" > "/proc/irq/$irq/smp_affinity"
    done
}

enable_affinity() {
    # RX: 4 个接收中断均匀分配到 4 核
    set_affinity 'reo2host-destination-ring1' 0 1
    set_affinity 'reo2host-destination-ring2' 1 1
    set_affinity 'reo2host-destination-ring3' 2 1
    set_affinity 'reo2host-destination-ring4' 3 1

    # TX 完成: 分配到 CPU 1-3
    set_affinity 'wbm2host-tx-completions-ring1' 1 1
    set_affinity 'wbm2host-tx-completions-ring2' 2 1
    set_affinity 'wbm2host-tx-completions-ring3' 3 1

    # WiFi PPDU MAC: 分配到 CPU 1-3
    set_affinity 'ppdu-end-interrupts-mac1' 1 1
    set_affinity 'ppdu-end-interrupts-mac2' 2 1
    set_affinity 'ppdu-end-interrupts-mac3' 3 1

    # EDMA (LAN/WAN): 全部绑定 CPU 3
    set_affinity 'edma_txcmpl' 3 1
    set_affinity 'edma_rxfill' 3 1
    set_affinity 'edma_rxdesc' 3 1
    set_affinity 'edma_misc' 3 1

    # NSS 硬件引擎: 分配到 CPU 2-3
    set_affinity 'nss_queue0' 2-3 1

    # DMA 引擎: 分配到 CPU 1-3
    set_affinity 'bam_dma' 1 1
    set_affinity 'bam_dma' 2 2
    set_affinity 'bam_dma' 3 3
}

boot() {
    local enable
    config_load smp_affinity
    config_get_bool enable "general" enable 1
    config_get_bool enable_log "general" enable_log 1
    [ "$enable" -eq 1 ] && enable=true || enable=false
    [ "$enable_log" -eq 1 ] && enable_log=true || enable_log=false
    $enable && enable_affinity
}
SMPEOF
  chmod +x "$QUALCOMMAX_DIR/base-files/etc/init.d/smp_affinity"

  # UCI 配置：默认启用 SMP Affinity
  mkdir -p "$QUALCOMMAX_DIR/base-files/etc/config"
  cat > "$QUALCOMMAX_DIR/base-files/etc/config/smp_affinity" <<'EOF'
config smp_affinity 'general'
    option enable '1'
    option enable_log '1'
EOF
fi

# ============================================
# 16. NSS 驱动启动优先级
#     提前 NSS 驱动启动，确保在网络服务之前就绑好
#     来源: ZqinKing/wrt_release
# ============================================
NSS_DRV_INIT="package/feeds/nss_packages/qca-nss-drv/files/qca-nss-drv.init"
if [ -f "$NSS_DRV_INIT" ]; then
  sed -i 's/START=.*/START=88/g' "$NSS_DRV_INIT"
  echo ">>> NSS 驱动启动优先级已调整 (START=88)"
fi

# ============================================
# 17. pbuf auto_scale off + schedutil 调度
#     关闭 WiFi 缓冲区自动缩放，固定分配更稳定
#     CPU 调度策略从 performance 改为 schedutil 更省电
#     来源: ZqinKing/wrt_release
# ============================================
PBUF_UCI="package/kernel/mac80211/files/pbuf.uci"
if [ -f "$PBUF_UCI" ]; then
  sed -i "s/auto_scale '1'/auto_scale 'off'/g" "$PBUF_UCI"
  sed -i "s/scaling_governor 'performance'/scaling_governor 'schedutil'/g" "$PBUF_UCI"
  echo ">>> pbuf auto_scale 已关闭, CPU 调度改为 schedutil"
fi

echo ">>> DIY 脚本执行完成"
