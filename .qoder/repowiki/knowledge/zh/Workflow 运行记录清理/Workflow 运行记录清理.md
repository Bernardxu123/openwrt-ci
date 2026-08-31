---
kind: external_dependency
name: Workflow 运行记录清理
slug: delete-workflow-runs
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
---

使用 Mattraks/delete-workflow-runs@main Action 自动清理旧的 GitHub Actions 运行记录，保留最近 3 天的运行日志，最少保留 3 次运行记录。防止 GitHub Actions 存储配额被历史日志占满。