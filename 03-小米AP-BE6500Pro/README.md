# 03 · 小米 AP BE6500 Pro（无线）

主路由的 WiFi 之外，家里另有一台小米 BE6500 Pro 作为**旁挂 AP、有线回程**。

## 现状
- IP **192.168.31.138**（设备上自配静态，不是 DHCP 租约）
- SoC IPQ5332，原厂系统（不是 OpenWrt 插件体系，别想着装 luci 包）
- SSID 与主路由统一：`bernard`（2.4G）/ `bernard_5G`（5G）；另有 MIoT 隔离 SSID
- 主路由：2.4G `ch6/HE20`、5G `ch149/HE80`（**country 必须是 CN**，否则 ch149 是 NO-IR）
- AP：2.4G `ch1/HT40`、5G `ch36/160`
- **Telnet 23 故意保留**作备用通道（root/admin，auto_ssh cron 自愈）

## 文档
| 文件 | 内容 |
|---|---|
| `无线信道规划审计-2026-10-22.md` | 信道重叠、2.4G 干扰源（AP HT40 + 邻居 + 微波炉）、5G 160MHz 结论 |
| `wifi-report-2026-10-19.md` | 换机当天的 WiFi 实测与调参记录 |

## 注意
- 手机/平板都是**随机 MAC**，关掉"随机 MAC"才能让静态租约稳定
- 不要用 UCI `bh_ap_2g/5g.disabled` 关 MiMesh 回程（实测会导致 AP 主 SSID 消失）；要关走小米后台
