# JDCloud RE-SS-01 (魔改亚瑟) OpenWrt 刷机指南

## 📋 设备信息

- **设备型号**: JDCloud RE-SS-01 (魔改版)
- **处理器**: Qualcomm IPQ6010 (4x Cortex-A53 @1.8GHz)
- **内存**: 1GB DDR4 (南亚 NT5AD512M16C4-JR)
- **存储**: 128GB eMMC (HIKSEMI)

## 📦 固件下载

编译完成后，访问 [Releases 页面](https://github.com/Bernardxu123/openwrt-ci/releases/tag/IPQ60XX-JDCloud-RE-SS-01) 下载固件。

**固件文件**：
- `openwrt-qualcommax-ipq60xx-jdcloud_re-ss-01-squashfs-nand-factory.bin` - **出厂刷机用**
- `openwrt-qualcommax-ipq60xx-jdcloud_re-ss-01-squashfs-nand-sysupgrade.bin` - **升级用**

---

## 🔧 刷机方法

### 方法一：Web 界面刷机（推荐）

适用于已刷入 OpenWrt 系统的设备。

1. **登录路由器**
   - 访问：`http://192.168.1.1`（或当前路由器 IP）
   - 账号：`root`
   - 密码：（当前系统密码）

2. **上传固件**
   - 进入：`系统` → `备份/升级` → `刷写新固件`
   - 点击 `选择文件`，选择下载的 **sysupgrade.bin** 固件
   - ⚠️ **不要勾选** "保留配置"（除非确定兼容）
   - 点击 `刷写固件`

3. **等待重启**
   - 刷机过程约 **3-5 分钟**
   - 重启后访问 `http://192.168.1.1`
   - 默认密码：`password`

---

### 方法二：SSH 命令刷机

适用于已有 SSH 访问权限的 OpenWrt 系统。

1. **上传固件到路由器**
   ```bash
   # 在本地电脑执行
   scp openwrt-*.sysupgrade.bin root@192.168.1.1:/tmp/
   ```

2. **SSH 登录路由器**
   ```bash
   ssh root@192.168.1.1
   ```

3. **执行刷机命令**
   ```bash
   # 备份配置（可选）
   sysupgrade -b /tmp/backup-$(date +%Y%m%d).tar.gz
   
   # 刷机（不保留配置）
   sysupgrade -n /tmp/openwrt-*.sysupgrade.bin
   
   # 或保留配置刷机（谨慎使用）
   sysupgrade /tmp/openwrt-*.sysupgrade.bin
   ```

4. **等待重启**
   - 设备会自动重启
   - 进度可通过串口或 SSH 重连监控

---

### 方法三：U-Boot 刷机（救砖用）

适用于系统无法启动或需要恢复出厂固件的情况。

#### 准备工作

- **硬件**：USB 转 TTL 串口线
- **软件**：PuTTY 或 SecureCRT
- **固件**：`factory.bin` 文件
- **TFTP 服务器**：本地电脑需搭建（推荐使用 Tftpd64）

#### 刷机步骤

1. **连接串口**
   - 打开路由器外壳，找到 UART 调试口
   - 连接顺序：`GND` → `RX` → `TX`（3.3V 不连接）
   - 波特率：`115200`，数据位 `8`，停止位 `1`，无校验

2. **进入 U-Boot**
   - 打开串口软件
   - 给路由器上电
   - 看到启动信息时，**快速按任意键**进入 U-Boot

3. **配置 IP 地址**
   ```bash
   # 设置路由器 IP
   setenv ipaddr 192.168.1.1
   
   # 设置电脑 IP（TFTP 服务器地址）
   setenv serverip 192.168.1.100
   
   # 保存设置
   saveenv
   ```

4. **TFTP 下载固件**
   ```bash
   # 下载固件到内存
   tftpboot 0x44000000 openwrt-qualcommax-ipq60xx-jdcloud_re-ss-01-squashfs-nand-factory.bin
   ```

5. **写入 Flash**
   ```bash
   # 擦除分区
   nand erase 0x0 0x10000000
   
   # 写入固件
   nand write 0x44000000 0x0 ${filesize}
   
   # 重启
   reset
   ```

6. **等待启动**
   - 首次启动约需 **2-3 分钟**
   - 串口会显示启动日志
   - 启动完成后访问 `http://192.168.1.1`

---

## ⚙️ 首次配置

### 1. 登录系统

- **Web 地址**：`http://192.168.1.1`
- **默认用户名**：`root`
- **默认密码**：`password`

### 2. 修改密码

1. 进入：`系统` → `管理权`
2. 设置新密码并保存

### 3. 配置网络

#### 3.1 WAN 口设置（PPPoE 拨号）

1. 进入：`网络` → `接口` → `WAN`
2. 协议选择：`PPPoE`
3. 填入宽带账号密码
4. 保存并应用

#### 3.2 IPv6 设置

1. 进入：`网络` → `接口` → `WAN6`
2. 协议：`DHCPv6 客户端`
3. 启用并保存

### 4. 无线配置

1. 进入：`网络` → `无线`
2. 启用 WiFi 并设置：
   - **SSID**：自定义名称
   - **加密**：`WPA2-PSK`
   - **密码**：自定义密码（至少 8 位）
3. 保存并应用

---

## 🚀 功能配置

### Docker 配置

1. 进入：`服务` → `Docker`
2. 检查 Docker 服务状态
3. 通过 `ttyd` 终端安装容器：
   ```bash
   docker pull nginx
   docker run -d -p 8080:80 nginx
   ```

### Passwall 代理

1. 进入：`服务` → `Passwall`
2. 添加节点
3. 启用服务

### Lucky DDNS

1. 进入：`服务` → `Lucky`
2. 配置 DDNS 服务
3. 设置端口转发规则

### Samba 文件共享

1. 进入：`服务` → `网络共享`
2. 启用 Samba4
3. 添加共享目录
4. Windows 访问：`\\192.168.1.1`

---

## 🛡️ 安全建议

1. **立即修改默认密码**
2. **关闭 WAN 口 SSH 访问**（仅允许 LAN）
3. **启用防火墙**
4. **定期备份配置**：
   ```bash
   sysupgrade -b /tmp/backup-$(date +%Y%m%d).tar.gz
   ```
5. **使用强密码**（WiFi、管理密码）

---

## 🔍 常见问题

### Q1: 刷机后无法访问 192.168.1.1？

**解决**：
1. 检查电脑 IP 是否在 `192.168.1.x` 网段
2. 手动设置电脑 IP 为 `192.168.1.100`，网关 `192.168.1.1`
3. 尝试 `ping 192.168.1.1` 测试连通性

### Q2: 刷机失败或变砖？

**解决**：
1. 通过串口进入 U-Boot
2. 使用 **方法三** 重新刷入 factory.bin

### Q3: WiFi 信号弱或无法连接？

**解决**：
1. 检查无线驱动是否正常加载：
   ```bash
   dmesg | grep ath11k
   ```
2. 重启无线：
   ```bash
   wifi reload
   ```

### Q4: Docker 容器无法启动？

**解决**：
1. 检查可用内存：
   ```bash
   free -h
   ```
2. 清理不用的容器：
   ```bash
   docker system prune -a
   ```

### Q5: 如何恢复出厂设置？

**方法一（Web）**：
- `系统` → `备份/升级` → `恢复出厂设置`

**方法二（SSH）**：
```bash
firstboot
reboot
```

---

## 📝 备份与恢复

### 备份配置

```bash
# SSH 登录后执行
sysupgrade -b /tmp/backup-$(date +%Y%m%d).tar.gz

# 下载到本地
scp root@192.168.1.1:/tmp/backup-*.tar.gz ./
```

### 恢复配置

1. 刷机时勾选 "保留配置"
2. 或刷机后在 Web 界面上传备份文件：
   - `系统` → `备份/升级` → `恢复备份`

---

## 📞 技术支持

- **项目地址**：[Bernardxu123/openwrt-ci](https://github.com/Bernardxu123/openwrt-ci)
- **上游项目**：[LiBwrt/openwrt-6.x](https://github.com/LiBwrt/openwrt-6.x)
- **问题反馈**：[Issues](https://github.com/Bernardxu123/openwrt-ci/issues)

---

*刷机指南版本: v1.0*  
*设备型号: JDCloud RE-SS-01 (魔改版)*  
*固件标签: IPQ60XX-JDCloud-RE-SS-01*
