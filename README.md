# OpenWrt 固件编译 - JDCloud RE-SS-01 魔改亚瑟

[![Build Status](https://github.com/Bernardxu123/openwrt-ci/actions/workflows/IPQ60XX-24.10-6.12-WIFI.yml/badge.svg)](https://github.com/Bernardxu123/openwrt-ci/actions)

基于 [LiBwrt/openwrt-6.x](https://github.com/LiBwrt/openwrt-6.x) 的定制固件，`main-nss` 分支，内核 6.12 + 满血 NSS 硬件加速。

## 设备规格

| 项目 | 规格 |
|------|------|
| 型号 | JDCloud RE-SS-01 (魔改亚瑟) |
| CPU | Qualcomm IPQ6010 (4x A53 @1.8GHz) |
| 内存 | 1GB DDR4 |
| 存储 | 128GB eMMC |
| 内核 | 6.12 + NSS v11.4 硬件加速 |

## 预装功能

| 类别 | 软件包 |
|------|--------|
| 代理 | OpenClash (Meta内核), Passwall (Xray/SingBox) |
| DNS | MosDNS, dnsmasq-full |
| 网络 | Lucky (DDNS/STUN/端口转发), UPnP |
| 文件 | Samba4 (NAS文件共享), Filemanager, SFTP |
| 系统 | TTYD 终端, Argon 主题 |

## NSS 硬件加速

- 6.12 内核适配 NSS v11.4 固件
- SKB Recycler 多核回收 + ECM 前端加速
- WiFi Offload / IPv6 / Bridge / VLAN / PPPoE 全系 NSS 驱动
- MCS / IGS / L2TPv2 / LAG / PPTP 高级加速模块
- 预置 `/usr/bin/nss-status` 诊断脚本

## 内核与网络优化

- TCP Fast Open (客户端+服务端模式)
- 空闲连接不重置慢启动
- PPPoE MTU 路径自动探测
- 连接跟踪表扩容至 163840
- 网络缓冲区增大 (16MB rmem/wmem)
- zram swap + swappiness=10 内存策略

## 默认信息

| 项目 | 值 |
|------|-----|
| 默认 IP | 192.168.31.1 |
| 默认用户 | root |
| 默认密码 | password |

## 使用方法

### 自动编译

1. Fork 本仓库
2. 进入 Actions → IPQ60XX-24.10-6.12-WIFI
3. 点击 Run workflow 手动触发，或推送代码自动编译

### 触发路径

修改以下文件推送后自动触发编译：
- `configs/ipq60xx-6.12-wifi.config`
- `libwrt.sh`
- `feeds/6.12.txt`
- `.github/workflows/IPQ60XX-24.10-6.12-WIFI.yml`

### 升级固件

```bash
# 下载 sysupgrade 固件，上传到路由器 /tmp
scp libwrt-*-sysupgrade.bin root@192.168.31.1:/tmp/

# 刷新固件 (不保留旧配置)
ssh root@192.168.31.1 sysupgrade -n -v /tmp/libwrt-*-sysupgrade.bin
```

## 项目结构

```
.
├── .github/workflows/    # GitHub Actions 工作流
├── configs/              # 设备编译配置 (.config)
├── feeds/                # Feeds 软件源配置
├── libwrt.sh             # DIY 定制脚本 (sysctl/NSS诊断/Samba预置)
├── scripts/              # 预设脚本和补丁
├── FLASH_GUIDE.md        # 刷机指南
└── README.md
```

## SSH 诊断

```bash
# 查看 NSS 硬件加速状态
nss-status

# 查看系统优化参数
cat /etc/sysctl.d/99-optimize.conf

# DNS 延迟测试
for ip in 223.5.5.5 119.29.29.29 210.22.70.3; do
  ping -c 1 $ip | grep time=
done
```

## 致谢

- [LiBwrt/openwrt-6.x](https://github.com/LiBwrt/openwrt-6.x)
- [breeze303/openwrt-ci](https://github.com/breeze303/openwrt-ci)
- [jerrykuku/luci-theme-argon](https://github.com/jerrykuku/luci-theme-argon)
- [sirpdboy/luci-app-lucky](https://github.com/sirpdboy/luci-app-lucky)
- [sbwml/luci-app-mosdns](https://github.com/sbwml/luci-app-mosdns)
