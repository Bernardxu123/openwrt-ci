#!/bin/sh
# src-compare.sh — 横向对比各优选源在「本机出口」下的质量（一次性评估用）
UA='Mozilla/5.0'
SNI='gogo.290490.xyz'
PER_SRC=20          # 每个源最多探多少条
WORK=/tmp/srccmp
rm -rf $WORK; mkdir -p $WORK

SRCS="tiancheng-hk|https://bestcf.pages.dev/tiancheng/hk.txt
tiancheng3-hk|https://bestcf.pages.dev/tiancheng3/hk.txt
mjz-cu|https://cf.junzhen.qzz.io/best_ips.txt
lz-cu|https://raw.githubusercontent.com/love-ztm/cfip/refs/heads/main/ubest_ips.txt
cmapi-cu|https://090227.pages.dev/bestcf?isp=cu&ips=50
wetest|https://bestcf.pages.dev/wetest/ipv4.txt
vvhan|https://bestcf.pages.dev/vvhan/ipv4.txt
gslege|https://bestcf.pages.dev/gslege/Cfxyz.txt
lancelot-top20|https://raw.githubusercontent.com/LancelotRar/best-cf-ips/refs/heads/main/best-cf-ip-scanned-top20.txt
jiechao|https://raw.githubusercontent.com/JieChaoCC/cf-ip-auto/refs/heads/main/data/ipapi.txt"

probe() {
  hp=$1; out=$2
  ip=${hp%:*}; port=${hp#*:}
  [ -z "$ip" ] || [ -z "$port" ] && return
  t0=$(awk '{print $1}' /proc/uptime)
  if echo | timeout 5 openssl s_client -connect "$ip:$port" -servername "$SNI" >/dev/null 2>&1; then
    t1=$(awk '{print $1}' /proc/uptime)
    awk -v a="$t0" -v b="$t1" -v hp="$hp" 'BEGIN{printf "%d %s\n",(b-a)*1000,hp}' >> "$out"
  else
    printf '99999 %s\n' "$hp" >> "$out"
  fi
}

echo "$SRCS" | while IFS='|' read -r name url; do
  [ -z "$name" ] && continue
  f="$WORK/$name.txt"
  curl -sf -m 20 -A "$UA" "$url" -o "$f" 2>/dev/null
  total=$(awk '{sub(/\r$/,"")} NF && $1 !~ /^#/' "$f" 2>/dev/null | cut -d'#' -f1 | grep -c ':')
  head -n "$PER_SRC" <(awk '{sub(/\r$/,"")} NF && $1 !~ /^#/ {print $1}' "$f" | cut -d'#' -f1) > "$WORK/$name.cand"
  : > "$WORK/$name.res"
  while read -r hp; do [ -n "$hp" ] && probe "$hp" "$WORK/$name.res" & done < "$WORK/$name.cand"
  wait
  sort -n "$WORK/$name.res" > "$WORK/$name.sorted"
  ok=$(grep -vc '^99999' "$WORK/$name.sorted" 2>/dev/null || echo 0)
  best=$(head -3 "$WORK/$name.sorted" | tr '\n' ' ')
  med=$(sed -n '3p' "$WORK/$name.sorted" | awk '{print $1}')
  nets=$(awk '{split($2,a,":"); split(a[1],b,"."); print b[1]"."b[2]"."b[3]}' "$WORK/$name.sorted" | sort -u | wc -l)
  printf '%-16s 条目=%-4s 探%-3s 活%-3s 中位=%sms /24数=%-3s 最快: %s\n' \
    "$name" "$total" "$(wc -l < "$WORK/$name.cand")" "$ok" "$med" "$nets" "$best"
done
