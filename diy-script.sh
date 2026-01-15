#!/bin/bash

# ============================================
# OpenWrt 自定义脚本 - JDCloud RE-SS-01 专用
# 基于 breeze303/openwrt-ci
# ============================================

# 修改默认IP (可选，取消注释以启用)
# sed -i 's/192.168.1.1/192.168.2.1/g' package/base-files/files/bin/config_generate

# 移除要替换的包 (保持原有逻辑)
rm -rf feeds/packages/net/mosdns
rm -rf feeds/packages/net/msd_lite
rm -rf feeds/packages/net/smartdns
rm -rf feeds/luci/themes/luci-theme-argon
rm -rf feeds/luci/themes/luci-theme-netgear
rm -rf feeds/luci/applications/luci-app-mosdns
rm -rf feeds/luci/applications/luci-app-netdata
rm -rf feeds/luci/applications/luci-app-serverchan

# ============================================
# Git稀疏克隆函数 (保留原项目逻辑)
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
# 1. 添加 Lucky (gdy666) - DDNS/端口转发/STUN
# ============================================
echo ">>> 正在添加 Lucky ..."
git clone --depth=1 https://github.com/gdy666/luci-app-lucky.git package/lucky-src
mv package/lucky-src/luci-app-lucky package/luci-app-lucky
mv package/lucky-src/lucky package/lucky
rm -rf package/lucky-src

# ============================================
# 2. 添加 Nikki (Mihomo 透明代理)
# ============================================
echo ">>> 正在添加 Nikki (Mihomo) ..."
git clone --depth=1 https://github.com/nikkinikki-org/OpenWrt-nikki.git package/nikki-src
mv package/nikki-src/luci-app-nikki package/luci-app-nikki
mv package/nikki-src/nikki package/nikki
rm -rf package/nikki-src

# ============================================
# 3. 添加其他插件
# ============================================

# AdGuard Home
git clone --depth=1 https://github.com/kongfl888/luci-app-adguardhome package/luci-app-adguardhome

# 微信推送
git clone --depth=1 -b openwrt-18.06 https://github.com/tty228/luci-app-wechatpush package/luci-app-serverchan

# iKoolProxy 广告过滤
git clone --depth=1 https://github.com/ilxp/luci-app-ikoolproxy package/luci-app-ikoolproxy

# 关机按钮
git clone --depth=1 https://github.com/esirplayground/luci-app-poweroff package/luci-app-poweroff

# Argon 主题及配置
git clone --depth=1 https://github.com/jerrykuku/luci-theme-argon package/luci-theme-argon
git clone --depth=1 https://github.com/jerrykuku/luci-app-argon-config package/luci-app-argon-config

# 系统工具 - 文件管理器
git_sparse_clone main https://github.com/kiddin9/kwrt-packages luci-app-filemanager

# sbwml 的 MosDNS
git_sparse_clone master https://github.com/sbwml/luci-app-mosdns luci-app-mosdns mosdns v2dat

# ============================================
# 4. 修复 Makefile 路径
# ============================================
find package/*/ -maxdepth 2 -path "*/Makefile" | xargs -i sed -i 's/..\/..\/luci.mk/$(TOPDIR)\/feeds\/luci\/luci.mk/g' {}
find package/*/ -maxdepth 2 -path "*/Makefile" | xargs -i sed -i 's/..\/..\/lang\/golang\/golang-package.mk/$(TOPDIR)\/feeds\/packages\/lang\/golang\/golang-package.mk/g' {}
find package/*/ -maxdepth 2 -path "*/Makefile" | xargs -i sed -i 's/PKG_SOURCE_URL:=@GHREPO/PKG_SOURCE_URL:=https:\/\/github.com/g' {}
find package/*/ -maxdepth 2 -path "*/Makefile" | xargs -i sed -i 's/PKG_SOURCE_URL:=@GHCODELOAD/PKG_SOURCE_URL:=https:\/\/codeload.github.com/g' {}

# 取消主题默认设置
find package/luci-theme-*/* -type f -name '*luci-theme-*' -print -exec sed -i '/set luci.main.mediaurlbase/d' {} \;

# ============================================
# 5. 更新并安装 Feeds
# ============================================
./scripts/feeds update -a
./scripts/feeds install -a

echo ">>> DIY 脚本执行完成"
