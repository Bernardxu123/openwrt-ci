#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cfhk-rotate-sub.sh 港新混合补丁：候选源加 tiancheng/sg.txt、过滤 HK|SG、命名按地区前缀。"""
import io

RAW = open("cfhk-sub-live2.sh", "rb").read().replace(b"\r\n", b"\n").decode("utf-8")
lines = RAW.split("\n")
# 第一行是 ssh_run 的命令回显，剥掉
if lines[0].startswith("$ cat /usr/bin/cfhk-rotate-sub.sh"):
    lines = lines[1:]
src = "\n".join(lines)
orig = src


def rep(old, new, tag):
    global src
    assert old in src, "模式未匹配: " + tag
    src = src.replace(old, new)
    print("OK:", tag)


# 1) 头部注释：说明港新混合
rep(
    "# 空选号保护、上传重试、回检时序；daed 侧每小时订阅 cron 已关。",
    "# 空选号保护、上传重试、回检时序；daed 侧每小时订阅 cron 已关。\n"
    "# 2026-09-29：候选池扩为 香港+新加坡 双地区（实测两者在你家出口延迟相当，SG 中位略优），\n"
    "# 选号纯按延迟+去相关、不分地区；节点名按实际地区前缀 HK-N / SG-N。",
    "头部注释",
)

# 2) SRCS 加 tiancheng/sg.txt + REGIONS 过滤变量
rep(
    "UA='Mozilla/5.0'\n"
    "# 主源：junzhen best_ips（用户指定，多地区+带宽标注，更新快）\n"
    "# 天诚 hk.txt 仅作 junzhen 拉不到时的兜底\n"
    "SRCS='https://cf.junzhen.qzz.io/best_ips.txt\n"
    "https://bestcf.pages.dev/tiancheng/hk.txt'",
    "UA='Mozilla/5.0'\n"
    "# 主源：junzhen best_ips（多地区+带宽标注，更新快）；天诚 hk.txt / sg.txt 为港新两地候选\n"
    "SRCS='https://cf.junzhen.qzz.io/best_ips.txt\n"
    "https://bestcf.pages.dev/tiancheng/hk.txt\n"
    "https://bestcf.pages.dev/tiancheng/sg.txt'\n"
    "# 只收备注命中这些地区的候选（整行 remark 判；改 'HK' 即回到纯香港）\n"
    "REGIONS='HK|SG'",
    "SRCS+REGIONS",
)

# 3) 过滤正则改用 REGIONS 变量
rep(
    "  | awk -F'#' '($2==\"\") || (toupper($2) ~ /HK/) {print $1}' | sort -u > \"$WORK/cand.txt\"",
    "  | awk -F'#' -v regs=\"$REGIONS\" '($2==\"\") || (toupper($2) ~ regs) {print $1}' | sort -u > \"$WORK/cand.txt\"",
    "过滤正则",
)

# 4) 命名段：按地区前缀（HK-N / SG-N / 兜底 CF-N）
rep(
    ": > \"$WORK/named.txt\"\n"
    "i=0\n"
    "while read -r hp; do\n"
    "  [ -z \"$hp\" ] && continue\n"
    "  i=$((i+1))\n"
    "  echo \"${hp}#HK-${i} ${hp}\" >> \"$WORK/named.txt\"\n"
    "done < \"$WORK/new.sorted\"",
    ": > \"$WORK/named.txt\"\n"
    "hk_i=0; sg_i=0; ot_i=0\n"
    "while read -r hp; do\n"
    "  [ -z \"$hp\" ] && continue\n"
    "  # 地区前缀从候选整行备注判（整行 remark：天诚的「HK版/SG版」都在空格后，$1 里没有）\n"
    "  remark=$(grep -m1 -F \"${hp}#\" \"$WORK/hk.all\" | head -1 | cut -d'#' -f2-)\n"
    "  up=$(printf '%s' \"$remark\" | tr 'a-z' 'A-Z')\n"
    "  case \"$up\" in\n"
    "    *HK*) hk_i=$((hk_i+1)); pfx=\"HK-${hk_i}\" ;;\n"
    "    *SG*) sg_i=$((sg_i+1)); pfx=\"SG-${sg_i}\" ;;\n"
    "    *)    ot_i=$((ot_i+1)); pfx=\"CF-${ot_i}\" ;;\n"
    "  esac\n"
    "  echo \"${hp}#${pfx} ${hp}\" >> \"$WORK/named.txt\"\n"
    "done < \"$WORK/new.sorted\"",
    "命名前缀",
)

assert src != orig
io.open("cfhk-rotate-sub.sh", "w", encoding="utf-8", newline="\n").write(src)
print("港新混合补丁写入 cfhk-rotate-sub.sh")
