---
kind: external_dependency
name: OpenWrt 编译缓存加速
slug: cachewrtbuild
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

使用 HiGarfield/cachewrtbuild Action 实现 OpenWrt 工具链和 ccache 缓存，mixkey 设置为 libwrt-25.12-nss-jdcloud-re-ss-01，prefix 指向 OpenWrt 源码路径。该缓存机制显著缩短重复编译时间，避免每次重新下载和编译工具链。