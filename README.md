# OpenWrt 固件编译项目 - JDCloud RE-SS-01

基于 [breeze303/openwrt-ci](https://github.com/breeze303/openwrt-ci) 定制的 OpenWrt 固件编译项目。

## 📦 目标设备

- **设备型号**: JDCloud RE-SS-01 (魔改亚瑟)
- **处理器**: Qualcomm IPQ6010 (4x Cortex-A53 @1.8GHz)
- **内存**: 1GB DDR4
- **存储**: 128GB eMMC (HIKSEMI)
- **内核版本**: 6.12 (with WiFi & NSS)

## ✨ 预装功能

| 功能类型 | 软件包 |
|---------|--------|
| **代理工具** | Passwall, Nikki (Mihomo) |
| **网络工具** | Lucky (DDNS/STUN), MosDNS, AdGuard Home |
| **文件共享** | Samba4 |
| **系统功能** | IPv6, ZeroTier, TTYD |
| **主题** | Argon |

## 🚀 使用方法

### 方式一：Fork 后自动编译

1. Fork 本仓库到你的 GitHub 账户
2. 进入 Actions 页面
3. 选择 `IPQ60XX-24.10-6.12-WIFI` 工作流
4. 点击 `Run workflow` 触发编译

### 方式二：推送代码自动触发

修改以下任一文件后推送，将自动触发编译：
- `configs/ipq60xx-6.12-wifi.config`
- `diy-script.sh`
- `feeds/6.12.txt`

## 📁 项目结构

```
.
├── .github/workflows/        # GitHub Actions 工作流
├── configs/                  # 设备配置文件
├── feeds/                    # Feeds 源配置
├── scripts/                  # 辅助脚本
├── diy-script.sh            # DIY 定制脚本
├── build.sh                 # 编译脚本
└── libwrt.sh                # LiBwrt 额外脚本
```

## 🔧 自定义

### 修改默认 IP

编辑 `diy-script.sh`，取消注释以下行：
```bash
sed -i 's/192.168.1.1/192.168.2.1/g' package/base-files/files/bin/config_generate
```

### 启用 Docker

编辑 `configs/ipq60xx-6.12-wifi.config`，取消 Docker 相关配置的注释。

> ⚠️ **注意**: IPQ6010 仅有 512MB 内存，启用 Docker 可能导致内存紧张。

## 📝 固件信息

- **默认 IP**: 192.168.1.1
- **默认密码**: password
- **源码仓库**: [LiBwrt/openwrt-6.x](https://github.com/LiBwrt/openwrt-6.x)
- **源码分支**: 24.10-6.12

## 🙏 致谢

- [LiBwrt/openwrt-6.x](https://github.com/LiBwrt/openwrt-6.x)
- [breeze303/openwrt-ci](https://github.com/breeze303/openwrt-ci)
- [gdy666/luci-app-lucky](https://github.com/gdy666/luci-app-lucky)
- [nikkinikki-org/OpenWrt-nikki](https://github.com/nikkinikki-org/OpenWrt-nikki)
- [xiaorouji/openwrt-passwall](https://github.com/xiaorouji/openwrt-passwall)
