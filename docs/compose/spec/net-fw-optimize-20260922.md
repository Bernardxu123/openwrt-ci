---
feature: net-fw-optimize-20260922
status: delivered
updated: 2026-09-22
branch: master + openwrt-ci/main
commits: openwrt-ci a4fb2a9..0218a17；主仓 docs 821e5c7..46ded98（本定稿提交在其外）
---

# 本地网络与固件优化（2026-09-22）

> Project override：与既有规格一致，compose 工作直接在本工作区 `master` + 嵌套仓 `openwrt-ci/main` 交付（会话隔离禁止 `git worktree add`）。

## Report

**What was built** — 路由器侧一次性清理：删掉 `/tmp/daed-new.ipk`（22.7MB）并移除 OpenClash 的 4 条空 geo cron（服务已停用），保留 daed geo / daed-guard / wugui 三条有效任务。固件侧 `openwrt-ci`：`libwrt.sh` 预置 daed 从 `v2026.09.14/2026.09.12-r1` 升到 **`v2026.09.21/2026.09.20-r4`**（与路由器现役一致，luci 仍 1.15-r2）；README/MAINTENANCE/build.yml 的 NSS 现役描述从 v11.4 对齐为 **v12.5**；CI 硬校验补 `kmod-qca-nss-drv-qdisc`，软校验在 `$OPENWRT_PATH/files/`（注意 workflow 会 `mv files`）检查 daed 预置，并写 `GITHUB_STEP_SUMMARY` 成功/失败摘要。

**Verification** — 路由器清理后 `/tmp` 无 `*.ipk`、crontab 无 `openclash-cron-task`、三条有效 cron 仍在；`bash -n libwrt.sh` PASS；IPK URL `curl -I` 302（GitHub release 正常）；build.yml 断言：无 `$GITHUB_WORKSPACE/files`、有 `OPENWRT_PATH/files/usr/bin/daed` 与 `kmod-qca-nss-drv-qdisc` 与 STEP_SUMMARY、无 `NSS v11.4` 现役表述。独立审阅 2 轮：首轮 2 critical（验收 200 vs 302、软校验路径）已修，复审 APPROVE。

**Journey log** — ①workflow 在 Load Custom Configuration 里 `mv files $OPENWRT_PATH/files`，任何事后 `$GITHUB_WORKSPACE/files` 检查必空；②GitHub release 资产 `curl -I` 恒 302，验收勿写死 200；③OPTIMIZATION_LOG §8 的 11.4→12.5 等项其实早已进树，不必重做；④daed 预置版本要跟路由器现役对齐，否则刷机会降级。

1. **路由器运行残留**：`/tmp/daed-new.ipk`（22.7MB）占用 tmpfs；OpenClash 虽已停用（主力 daed），crontab 仍有 4 条每周 geo 更新任务在空跑。
2. **固件预置 daed 过时**：`libwrt.sh` 仍钉 `v2026.09.14` / `daed 2026.09.12-r1`，而上游 release **v2026.09.21** 已提供 `daed_2026.09.20-r4`（路由器现役即 r4）。下次刷机会把 daed 降回旧版。
3. **文档漂移**：README / build.yml 描述仍写 NSS **v11.4**，`configs/jdcloud_re_ss01.config` 已是 **12.5 测试轮**。
4. **CI 校验缺口**：`kmod-qca-nss-drv-qdisc` 未进硬校验清单（OPTIMIZATION_LOG §5#6）；构建成功后无版本摘要，排障要翻全日志。

用户拍板本轮范围：路由器仅「清理残留 + 关 OpenClash cron」；固件做「升 daed + 同步文档 + CI 增强」。**不做** tcp_notsent_lowat、NSS SQM、镜像裁剪冷备包、DL 缓存（10GB 上限可能挤掉 toolchain）。

## [S2] Design

### A. 路由器运行时（一次性 ops，无代码）

| 动作 | 命令/效果 |
|---|---|
| 删升级残留 | `rm -f /tmp/daed-new.ipk` |
| 关 OpenClash 空 cron | 从 `/etc/crontabs/root` 删除含 `openclash-cron-task` 的 4 行，`/etc/init.d/cron restart` |

保留：OpenClash **包**（冷备，init 已 disable）；不碰 wugui/daed-guard/geo-update cron。

### B. openwrt-ci 固件预置升级

`libwrt.sh` §28 版本变量：

```
DAED_REL_TAG="v2026.09.21"
DAED_VER="2026.09.20-r4"
LUCI_DAEDE_VER="1.15-r2"    # 上游该 tag 仍为 1.15-r2，不变
```

IPK URL 模式不变（`releases/download/${DAED_REL_TAG}/daed_${DAED_VER}_aarch64_cortex-a53.ipk`）。改版本仍只动这三行。

### C. 文档同步

- `README.md`：内核/NSS 描述改为与 `configs/jdcloud_re_ss01.config` 一致（NSS **12.5**，注明 12.x 无 802.11s mesh，需 mesh 回退 11.4）。
- `build.yml` Release notes 中「NSS v11.4」同步改掉。

### D. CI 增强（无密钥、无外部依赖）

1. **硬校验补 `kmod-qca-nss-drv-qdisc`**（与现有 kmod-nft-tproxy 等同列表，缺失 exit 1）。
2. **软校验补 daed 预置**：`files/usr/bin/daed` 存在性 + 可执行（warning 级，因走 files/ 不进 bin/*.ipk）。
3. **构建摘要**：Verify 通过后写 `$GITHUB_STEP_SUMMARY`（daed pin 版本、sysupgrade 路径、BTF ✓、qdisc ✓），失败时 `if: failure()` 再写一行失败摘要。**不做** Server酱/Telegram（需密钥）。

### 错误行为

- 路由器清理失败仅告警不回滚（幂等可重跑）。
- `libwrt.sh` 下载 daed/luci IPK 失败仍 `exit 1`（既有行为）。
- CI 校验失败禁止发布（既有硬门风格）。

### 测试边界

- 路由器：清理后 `ls /tmp/*.ipk` 为空；`grep openclash /etc/crontabs/root` 无匹配；daed/wugui/guard cron 仍在。
- 固件脚本：`bash -n libwrt.sh`；grep 确认三变量；IPK URL 可 HTTP 200（curl -I）。
- 文档：无残留「v11.4」表述（config 注释除外）。
- CI：YAML 语法（actionlint 若无则目视 + 结构完整）；不实际触发全量编译（数小时级）。

## [S3] Out of Scope

- tcp_notsent_lowat、NSS SQM、镜像裁剪 OpenClash/MosDNS/Passwall
- DL 缓存 / pin 上游 commit / 周自动构建 / 外部失败通知
- 路由器内核/NSS/daed 本体升级（路由器已是 r4）
- 合并 breeze303 上游（近期 x86-64 为主，shallow 无 merge-base）

## Tasks

- [x] T1: 路由器清理残留 ipk + 删除 OpenClash 空 cron — acceptance: `/tmp` 无 `*.ipk`；crontab 无 `openclash-cron-task`；wugui/daed-guard/geo cron 仍在 (covers: S2A)
- [x] T2: `libwrt.sh` daed 版本升到 v2026.09.21 / 2026.09.20-r4 — acceptance: 三变量正确；构造的 IPK URL `curl -I` 返回 **2xx/302**（GitHub release 资产 302 重定向 CDN 属正常） (covers: S2B)
- [x] T3: 同步 README 与 build.yml 的 NSS 版本描述 — acceptance: 用户可见文档不再写 NSS v11.4 为现役 (covers: S2C)
- [x] T4: CI 加 kmod-qdisc 硬校验、daed 预置软校验、STEP_SUMMARY — acceptance: build.yml 含三处改动且 YAML 结构完整 (covers: S2D; depends: T2)
