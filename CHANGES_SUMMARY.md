# 固件优化纠错 - 完整修改清单

## 📁 文件修改清单

### 1. libwrt.sh - 主要 DIY 脚本

**路径**: `libwrt.sh`

#### 修改 1.1: 添加 Passwall 依赖包 (第 2 步后)
```bash
# 在 "MosDNS" 后添加:
# Passwall 依赖包
git clone --depth=1 https://github.com/xiaorouji/openwrt-passwall-packages package/passwall-pkg-tmp
for pkg in chinadns-ng dns2socks microsocks ipt2socks v2ray-geodata v2ray-plugin simple-obfs shadow-tls tcping geoview; do
    [ -d "package/passwall-pkg-tmp/$pkg" ] && cp -rf "package/passwall-pkg-tmp/$pkg" package/
done
rm -rf package/passwall-pkg-tmp
```

#### 修改 1.2: 修复 Passwall patch 路径 (第 9 节)
```bash
# 旧: feeds/luci/applications/luci-app-passwall/luasrc/passwall/util_xray.lua
# 新: package/luci-app-passwall/luasrc/passwall/util_xray.lua
PASSWALL_UTIL="package/luci-app-passwall/luasrc/passwall/util_xray.lua"
```

#### 修改 1.3: 添加 IPv6 sysctl 参数 (第 6 节 sysctl.conf)
```bash
# 在 "连接跟踪" 后添加:
# === IPv6 完善 ===
net.ipv6.conf.all.disable_ipv6=0
net.ipv6.conf.default.disable_ipv6=0
net.ipv6.conf.all.forwarding=1
net.ipv6.conf.all.accept_ra=2
net.ipv6.conf.default.accept_ra=2
```

#### 修改 1.4: 修复 overcommit_memory (第 21 节)
```bash
# 旧: vm.overcommit_memory=1
# 新: vm.overcommit_memory=2  # 防止 OOM
vm.overcommit_memory=2
```

### 2. configs/jdcloud_re_ss01.config - 编译配置

**路径**: `configs/jdcloud_re_ss01.config`

#### 修改 2.1: 添加 kmod-nft-tproxy
```bash
# 在 "网络内核模块" 部分添加:
CONFIG_PACKAGE_kmod-nft-tproxy=y
CONFIG_PACKAGE_kmod-nf-tproxy=y
```

### 3. 新增文件: files/etc/uci-defaults/991_openclash_init

**路径**: `files/etc/uci-defaults/991_openclash_init`

```bash
#!/bin/sh
# OpenClash 初始化配置
[ -f /etc/config/openclash ] || {
    [ -d /usr/lib/lua/luci/controller/openclash ] || exit 0
    touch /etc/config/openclash
    uci add openclash config
}
uci set openclash.config.disable_udp_quic='0'
uci set openclash.config.ipv6_enable='1'
uci set openclash.config.ipv6_dns='1'
uci set openclash.config.enable_custom_dns='1'
uci set openclash.config.enable_meta_sniffer='1'
uci set openclash.config.enable_tcp_concurrent='1'
uci set openclash.config.enable_unified_delay='1'
uci set openclash.config.find_process_mode='always'
uci set openclash.config.stack_type='mixed'
uci set openclash.config.cachesize_dns='1'
uci commit openclash
```

### 4. 新增文件: preset-clash-core.sh (可选更新)

**路径**: `scripts/preset-clash-core.sh` 或 `files/etc/openclash/core/preset-clash-core.sh`

```bash
#!/bin/bash
# 2026 年 OpenClash 主要使用 Meta (Mihomo) 核心
mkdir -p files/etc/openclash/core
ARCH="${1:-arm64}"
META_URL="https://raw.githubusercontent.com/vernesong/OpenClash/core/master/meta/clash-linux-${ARCH}.tar.gz"

# Geo 数据
GEOIP_URL="https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat"
GEOSITE_URL="https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat"

# 下载 Meta 核心
wget -qO- "$META_URL" | tar xOvz > files/etc/openclash/core/clash_meta || {
    echo "::error::Failed to download Meta core"
    exit 1
}

# 兼容性: 将 meta 也作为默认 clash 核心
cp files/etc/openclash/core/clash_meta files/etc/openclash/core/clash

# Geo 数据
wget -qO "$GEOIP_URL" > files/etc/openclash/GeoIP.dat
wget -qO "$GEOSITE_URL" > files/etc/openclash/GeoSite.dat

chmod +x files/etc/openclash/core/clash*
echo ">>> OpenClash Meta core preset complete"
```

### 5. .github/workflows/build.yml

**路径**: `.github/workflows/build.yml`

#### 修改 5.1: 删除无效的 BBR echo
```yaml
# 在 "Download DL Package" 步骤中删除:
# echo "CONFIG_TCP_CONG_BBR=y" >> .config
# echo "CONFIG_NET_SCH_FQ=y" >> .config
```

#### 修改 5.2: 添加编译后包校验 (可选)
```yaml
- name: Verify packages
  run: |
    cd $OPENWRT_PATH
    MANIFEST=$(find bin/packages -name "Packages.manifest" | head -5)
    for pkg in luci-app-samba4 samba4-server luci-app-passwall xray-core; do
        if ! grep -rq "Package: $pkg" $MANIFEST 2>/dev/null; then
            echo "::error::$pkg missing from build output!"
            exit 1
        fi
    done
```

---

## 🔍 修改验证清单

- [ ] Passwall 依赖包在 feeds install 后存在
- [ ] kmod-nft-tproxy 在 .config 中启用
- [ ] IPv6 sysctl 参数正确
- [ ] overcommit_memory=2
- [ ] Passwall patch 路径正确
- [ ] OpenClash uci-defaults 991 无冲突
- [ ] preset-clash-core.sh 只下载 Meta 核心
- [ ] workflow 中无 BBR echo

---

## 📌 引用来源

| 来源 | URL |
|------|-----|
| LiBwrt/LibWrt | https://github.com/LiBwrt/LibWrt/tree/25.12-nss |
| breeze303/openwrt-ci | https://github.com/breeze303/openwrt-ci |
| ZqinKing/wrt_release | https://github.com/ZqinKing/wrt_release |
| laipeng668/openwrt-ci-roc | https://github.com/laipeng668/openwrt-ci-roc |
| robimarko/nss-packages | https://github.com/robimarko/nss-packages |

---

## ⚠️ 风险提示

1. **BBR 模块加载**: `modprobe tcp_bbr` 需确保 `CONFIG_TCP_CONG_BBR=y` (非 =m)
2. **git clone 重试**: CI 环境中 GitHub 网络波动，建议添加 retry 逻辑
3. **Passwall patch 路径**: 2026 年 Passwall 可能已重构文件结构
4. **OpenClash UCI 时序**: uci-defaults 在 postinst 之前执行需特殊处理
