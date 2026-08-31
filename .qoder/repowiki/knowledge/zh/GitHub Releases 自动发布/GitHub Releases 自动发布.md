---
kind: external_dependency
name: GitHub Releases 自动发布
slug: release-action
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

使用 ncipollo/release-action@v1 将编译产物自动发布到 GitHub Releases。固件文件名格式为 R${DATE}，包含 factory.bin 和 sysupgrade.bin 两种类型，同时生成 sha256sums 校验文件。Release body 包含详细的设备信息、内核版本、功能特性说明。