#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 cfhk-rotate-sub.sh 打 2026-09-27 修复补丁（六处）。"""
import io

RAW = open("cfhk-sub-live.sh", "rb").read().replace(b"\r\n", b"\n").decode("utf-8")
lines = RAW.split("\n")
assert lines[0].startswith("$ cat /usr/bin/cfhk-rotate-sub.sh"), lines[0]
src = "\n".join(lines[1:])
orig = src


def rep(old, new, tag):
    global src
    assert old in src, "模式未匹配: " + tag
    src = src.replace(old, new)
    print("OK:", tag)


# 1) 头部注释：cron 与本次修复说明
rep(
    "# cron：5,35 * * * * /usr/bin/cfhk-rotate-sub.sh   （每 30 分钟）",
    "# cron：5 5 * * * /usr/bin/cfhk-rotate-sub.sh      （每天 05:05 一轮）\n"
    "# 2026-09-27：修 compatibility 置空致隧道全灭、HK 专选、节点名带 HK、\n"
    "# 空选号保护、上传重试、回检时序；daed 侧每小时订阅 cron 已关。",
    "头部注释",
)

# 2) HK 过滤（按整行 remark 判，天诚的 HK版 在空格后）
rep(
    "awk '{sub(/\\r$/,\"\")} NF && $1 !~ /^#/ {print $1}' \"$WORK/hk.all\" | cut -d'#' -f1 | sort -u > \"$WORK/cand.txt\"",
    "# 只收备注含 HK 的条目（junzhen 多地区列表筛 HK；天诚 hk.txt 本身即 HK 池）。\n"
    "# 必须按整行 remark 判：天诚的\"HK版\"在空格后，$1 里没有。\n"
    "awk '{sub(/\\r$/,\"\")} NF && $1 !~ /^#/ {print}' \"$WORK/hk.all\" \\\n"
    "  | awk -F'#' '($2==\"\") || (toupper($2) ~ /HK/) {print $1}' | sort -u > \"$WORK/cand.txt\"",
    "HK过滤",
)

# 3) 带备注的 CSV（LIST 仍存裸地址）
rep(
    "sort \"$WORK/new.hp\" > \"$WORK/new.sorted\"\n"
    "NEWCSV=$(tr '\\n' ',' < \"$WORK/new.sorted\" | sed 's/,$//')",
    "sort \"$WORK/new.hp\" > \"$WORK/new.sorted\"\n"
    "NEWCSV=$(tr '\\n' ',' < \"$WORK/new.sorted\" | sed 's/,$//')\n"
    "# 带备注的 CSV（Worker 收集器支持 ip:port#备注，备注即订阅节点名 → HK-1 <ip>）；\n"
    "# LIST 仍写裸地址，否则回读时带备注永远比不过裸集合。\n"
    ": > \"$WORK/named.txt\"\n"
    "i=0\n"
    "while read -r hp; do\n"
    "  [ -z \"$hp\" ] && continue\n"
    "  i=$((i+1))\n"
    "  echo \"${hp}#HK-${i} ${hp}\" >> \"$WORK/named.txt\"\n"
    "done < \"$WORK/new.sorted\"\n"
    "NAMEDCSV=$(tr '\\n' ',' < \"$WORK/named.txt\" | sed 's/,$//')",
    "CSV带备注",
)

# 4) metadata 显式带 compatibility + 上传重试加固
rep(
    "if ! curl -sS --retry 3 --retry-delay 2 -m 60 -X PUT \\\n"
    "  -H \"Authorization: Bearer $TOK\" \\\n"
    "  -F 'metadata={\"main_module\":\"worker.js\",\"bindings\":[]};type=application/json' \\",
    "# metadata 显式带 compatibility：2026-09-27 事故就是部署时被置空，导致\n"
    "# new ReadableStream() 抛错、WS 隧道全灭。日期+flag 双保险，脚本上传即自愈。\n"
    "if ! curl -sS --retry-all-errors --retry 5 --retry-delay 3 -m 60 -X PUT \\\n"
    "  -H \"Authorization: Bearer $TOK\" \\\n"
    "  -F 'metadata={\"main_module\":\"worker.js\",\"bindings\":[],\"compatibility_date\":\"2024-09-23\",\"compatibility_flags\":[\"streams_enable_constructors\"]};type=application/json' \\",
    "compatibility+重试",
)

# 5) 空选号保护 + sed 改用带备注 CSV
rep(
    "# ---------- 5. 写 Worker（inline 优选地址） ----------\n"
    "sed \"s|let 优选地址 = '[^']*';|let 优选地址 = '$NEWCSV';|\" \"$BASE\" > /tmp/worker.js\n"
    "grep -q \"let 优选地址 = '$NEWCSV';\" /tmp/worker.js || { log \"ERROR sed 未替换优选地址\"; exit 1; }",
    "# ---------- 5. 写 Worker（inline 优选地址，带 HK 备注） ----------\n"
    "[ -s \"$WORK/new.hp\" ] || { log \"ERROR 选号为空（候选全判死/握手失败），放弃本轮\"; exit 1; }\n"
    "[ -n \"$NAMEDCSV\" ] || { log \"ERROR 带备注 CSV 为空，放弃本轮\"; exit 1; }\n"
    "sed \"s|let 优选地址 = '[^']*';|let 优选地址 = '$NAMEDCSV';|\" \"$BASE\" > /tmp/worker.js\n"
    "grep -q \"let 优选地址 = '$NAMEDCSV';\" /tmp/worker.js || { log \"ERROR sed 未替换优选地址\"; exit 1; }",
    "空选号保护",
)

# 6) 回检时序与措辞
rep("sleep 25\nresp=$(gql \"$DTOK\"",
    "sleep 210  # 等满一个 daed 检查周期（3min）；25 秒时首测还没跑\nresp=$(gql \"$DTOK\"",
    "回检时序")
rep(
    "if [ \"$ND\" -ge 3 ]; then\n"
    "  log \"WARN 回检 $ND/4 不通（假活），下一轮将排除：$(tr '\\n' ' ' < \"$WORK/check.dead\")\"\n"
    "else\n"
    "  log \"回检通过（不通 $ND/4）\"\n"
    "fi",
    "if [ \"$ND\" -ge 3 ]; then\n"
    "  log \"WARN 回检 $ND/4 暂不通（判死以下轮 daed nodeLatencies 为准）：$(tr '\\n' ' ' < \"$WORK/check.dead\")\"\n"
    "else\n"
    "  log \"回检记录：不通 $ND/4\"\n"
    "fi",
    "回检措辞",
)

assert src != orig
with io.open("cfhk-rotate-sub.sh", "w", encoding="utf-8", newline="\n") as f:
    f.write(src)
print("全部六处补丁写入 cfhk-rotate-sub.sh")
