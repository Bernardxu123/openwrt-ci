# OpenWrt 固件编译 - JDCloud RE-SS-01

[![Build Status](https://github.com/Bernardxu123/openwrt-ci/actions/workflows/IPQ60XX-24.10-6.12-WIFI.yml/badge.svg)](https://github.com/Bernardxu123/openwrt-ci/actions)

基于 [LiBwrt/openwrt-6.x](https://github.com/LiBwrt/openwrt-6.x) + [kenzok8/small-package](https://github.com/kenzok8/small-package) 的定制固件。

## 📦 设备规格

| 项目 | 规格 |
|------|------|
| **型号** | JDCloud RE-SS-01 (魔改亚瑟) |
| **CPU** | Qualcomm IPQ6010 (4x A53 @1.8GHz) |
| **内存** | 1GB DDR4 |
| **存储** | 128GB eMMC |
| **内核** | 6.12 + NSS 硬件加速 |

## ✨ 预装功能

| 类别 | 软件包 |
|------|--------|
| **代理** | OpenClash, Passwall |
| **网络** | Lucky, MosDNS, AdGuard Home, UPnP |
| **文件** | Samba4, Filemanager, SFTP |
| **系统** | TTYD, Argon 主题 |

> ⚠️ **Docker**: 仅预装内核依赖，需自行 `apk add docker` 安装

## 🚀 使用方法

### 自动编译
1. Fork 本仓库
2. 进入 **Actions** → **IPQ60XX-24.10-6.12-WIFI**
3. 点击 **Run workflow**

### 触发编译
修改以下文件后推送将自动触发：
- `configs/ipq60xx-6.12-wifi.config`
- `feeds/6.12.txt`
- `libwrt.sh`

## 📁 项目结构

```
.
├── .github/workflows/    # GitHub Actions 工作流
├── configs/              # 设备配置 (.config)
├── feeds/                # Feeds 软件源配置
├── libwrt.sh             # DIY 定制脚本
├── FLASH_GUIDE.md        # 刷机指南
└── README.md
```

## 📝 固件信息

| 项目 | 值 |
|------|-----|
| **默认 IP** | 192.168.1.1 |
| **默认密码** | password |
| **软件源** | 北京大学镜像 (PKU) |

## 🙏 致谢

- [LiBwrt/openwrt-6.x](https://github.com/LiBwrt/openwrt-6.x)
- [kenzok8/small-package](https://github.com/kenzok8/small-package)
- [breeze303/openwrt-ci](https://github.com/breeze303/openwrt-ci)
- [gdy666/luci-app-lucky](https://github.com/gdy666/luci-app-lucky)
