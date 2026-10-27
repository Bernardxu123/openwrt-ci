# 家庭网络工作区（导航）

> **给 AI：先读 `AGENTS.md`**（唯一事实源，含全部结论与铁律）。本文件只是目录导览。

## 快速上手

```powershell
python ssh_run.py 'uci show firewall | grep offload'   # 连主路由执行命令
```

- 账号密码 / 面板入口 → **`凭据.md`**
- 环境、拓扑、规则、踩坑判据 → **`AGENTS.md`**
- 最近改动与验证数据 → **`reports/`**

## 目录（按设备型号）

| 目录 | 是什么 | 体积 |
|---|---|---|
| `01-光猫-HG5585F/` | 光猫（现网主路由）刷机与救砖物料 | ~1.0 GB |
| ├ `刷机流程/` | 00–08 全流程文档 + 串口抓包日志 | 2.2 MB |
| ├ `原厂备份-CU/` `原厂备份-CT/` | **NAND 全分区镜像（唯一副本，勿删）** | 740 MB |
| ├ `固件/` | 可校验的 ponwrt 10-18 全套 + 原厂一键刷入包 + 引导件 | 280 MB |
| ├ `身份数据/` | LOID / MAC / 分区表 / 刷机记录 | — |
| ├ `工具/` | 开通道、xmodem 发送、fhtool 脚本 | — |
| └ `分析-CT/` | CT 版取证、PON debug bundle、pcap | 8 MB |
| `02-主路由-AN7581-QWRT/` | ├ `固件与镜像/` QWRT-R26.10.21 可用镜像<br>├ `分析报告/` PON/IRQ/硬件加速审计<br>├ `脚本/` 固件改造与校验<br>└ `备份/` 配置快照 | 91 MB |
| `03-小米AP-BE6500Pro/` | 无线信道规划审计、WiFi 实测报告 | 36 KB |
| `04-代理-nikki/` | ├ `profile/` 当前 mihomo profile 源 + 部署回滚<br>├ `规则快照/` daed 时代规则（历史对照）<br>├ `dsh-pocket-ipv6/` 远程入口部署件<br>└ `备份/` | 400 KB |
| `05-网络测绘-netplan/` | 家用 WiFi 测绘（`index.html` 可视化 / survey 脚本） | 1.6 MB |
| `reports/` | 当前技术栈的过程报告（9 篇） | 100 KB |
| `tools/` | 探针与一次性脚本（`probes/` 为历史探针） | 40 KB |
| `plugins/` | DSH 插件 `dsh-usage-stats` 源码 | 7.5 MB |

## 关于那 740MB 备份

`01-光猫-HG5585F/原厂备份-{CU,CT}/` 是两台光猫刷机**之前**抓的 NAND 全分区镜像，
刷完后不可再生，救砖只能靠它 —— 所以保留。若只想要纯文档仓库、不要这些镜像：

```powershell
New-Item -ItemType Directory -Force 'D:\AI\路由-资源备份' | Out-Null
Move-Item '01-光猫-HG5585F\原厂备份-CU','01-光猫-HG5585F\原厂备份-CT' 'D:\AI\路由-资源备份\'
```

## 维护规则

1. 新报告写进 `reports/`，命名 `主题-YYYYMMDD.md`；结论同时回写到 `AGENTS.md` 对应章节。
2. 只有**当前技术栈**的东西留在工作区；过期方案/旧栈配置移到 `D:\AI\_路由旧归档-<日期>\`。
3. 大文件（≥5MB）放对应型号目录，不放根目录；重复件一律删。
4. 根目录只放：`AGENTS.md`、`README.md`、`凭据.md`、`ssh_run.py`。
5. 本目录是 git 仓库（`git log` 可查历史），敏感凭据不要提交。
