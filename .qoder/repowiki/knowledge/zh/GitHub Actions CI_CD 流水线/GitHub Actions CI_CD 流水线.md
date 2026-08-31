---
kind: external_dependency
name: GitHub Actions CI/CD 流水线
slug: github-actions
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

使用 GitHub Actions 执行自动化固件编译流程，运行在 ubuntu-22.04 环境，超时时间 360 分钟。关键步骤包括：初始化编译环境、合并磁盘空间、克隆源码、应用补丁、下载依赖包、并行编译、整理固件文件、发布 Release。成功编译后自动执行 git merge dev --ff-only 将 dev 分支合并到 main 并推送。