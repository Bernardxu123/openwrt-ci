---
kind: external_dependency
name: LiBwrt LibWrt 固件源码基础
slug: libwrt-libwrt
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

本项目基于 LiBwrt/LibWrt 25.12-nss 分支构建，作为 OpenWrt 6.x 的定制发行版基础。工作流通过环境变量 REPO_URL 和 REPO_BRANCH 指定源码仓库地址和分支名，在编译时克隆到 openwrt 目录。该上游项目提供 IPQ60XX 平台支持、NSS v11.4 硬件加速驱动以及完整的内核配置框架。