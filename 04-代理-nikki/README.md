# 04 · 代理栈（nikki + mihomo）

现网代理 = **nikki 前端 + mihomo 核心**，跑在主路由上，透明代理全家设备。

## 现状速览
- `nikki 2026.10.10-1` + `luci-app-nikki 1.26.2-r1` + `mihomo v1.19.32`
- 数据面：**TCP redirect(7891)**、**UDP tproxy(7892)**；DNS 在 `:1053`（fake-ip `198.18.0.0/16` + `2001:2::/64`）
- **绕过大陆走内核**：nft `@china_ip`(7362 段)/`@china_ip6`(1655 段) 命中即 return，不进 mihomo
- 配置：`uci nikki.config.profile='file:openclash-20261022.yaml'` → `/etc/nikki/profiles/openclash-20261022.yaml`

## 目录
| 子目录 | 内容 |
|---|---|
| `profile/` | **当前 profile 源文件**（改这个，不要改 `/etc/nikki/run/config.yaml`）+ `部署与回滚-20261022.md` |
| `规则快照/` | `current/` 现役规则文本、`snapshots/` 历史版本（daed 时代，仅作对照） |
| `dsh-pocket-ipv6/` | DSH 手机端远程入口部署件（nginx.conf、init.d、DDNS 脚本、acme） |
| `备份/` | 迁 nikki 时的配置快照（openclash-20261022/final） |

## 三条最容易踩的坑（详见 AGENTS.md §7）
1. **`GOMEMLIMIT` 字段必须留空**：填 `80MiB` 会让整个 nikki 页面存不了；填纯数字更好不了（Go 会当字节数）
2. **内网主机名靠 `nameserver-policy "+.lan" → 192.168.31.1`**：LAN 的 `:53` 被劫持到 mihomo，dnsmasq 不参与客户端解析
3. **不要手改 `/etc/nikki/mixin.yaml`**（ucode 会覆盖），用 `uci set nikki.mixin.*`

## 改完的标准验证
```sh
/etc/init.d/nikki status; pidof mihomo
grep -cE "level=(error|fatal)" /var/log/nikki/core.log
nslookup www.baidu.com 192.168.31.1     # 真实国内 IP
nslookup www.google.com 192.168.31.1    # 198.18.x（fake-ip）
nslookup tablet.lan 192.168.31.1        # 192.168.31.122（内网名）
```
