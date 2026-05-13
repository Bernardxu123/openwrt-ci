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
# 5. 预置内核优化参数
# ============================================
mkdir -p files/etc/sysctl.d
cat > files/etc/sysctl.d/99-optimize.conf <<EOF
# 内存：优先使用物理内存，减少 zram 压缩开销
vm.swappiness=10
# TCP Fast Open (客户端+服务端模式)
net.ipv4.tcp_fastopen=3
# TCP 空闲连接不重置慢启动
net.ipv4.tcp_slow_start_after_idle=0
# BBR 拥塞控制 (对 OpenClash 出海流量生效，不影响 NSS 硬件加速)
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
EOF

echo ">>> DIY 脚本执行完成"
