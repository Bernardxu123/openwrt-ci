#!/bin/sh
# sgtest.sh — HK vs SG 优选池在本机出口的握手延迟对比（只读探测，不动 daed/worker）
UA='Mozilla/5.0'
WORK=/tmp/sgtest
rm -rf $WORK; mkdir -p $WORK
SNI=gogo.290490.xyz

for u in "https://bestcf.pages.dev/tiancheng/hk.txt" \
         "https://bestcf.pages.dev/tiancheng/sg.txt" \
         "https://cf.junzhen.qzz.io/best_ips.txt"; do
  curl -sf --retry 2 -m 25 -A "$UA" "$u" >> "$WORK/all.txt" || echo "WARN 拉取失败: $u"
done
[ -s "$WORK/all.txt" ] || { echo "ERROR 无候选"; exit 1; }

# 按注释里的地区标签拆池（整行 remark 判，HK 版/SG 版都在空格后）
awk '{sub(/\r$/,"")} NF && $1 !~ /^#/ {print}' "$WORK/all.txt" | awk -F'#' '
  { r=$2; up=toupper(r); reg="other";
    if (up ~ /HK/) reg="HK";
    else if (up ~ /SG/) reg="SG";
    print reg "\t" $1 }' | sort -u > "$WORK/pool.tsv"
grep '^HK' "$WORK/pool.tsv" | cut -f2 > "$WORK/hk.hp"
grep '^SG' "$WORK/pool.tsv" | cut -f2 > "$WORK/sg.hp"
echo "池大小：HK=$(wc -l < $WORK/hk.hp) SG=$(wc -l < $WORK/sg.hp)"

probe() { # $1=file $2=out
  : > "$2"
  N=0
  while read -r hp; do
    [ -z "$hp" ] && continue
    (
      ip=${hp%:*}; port=${hp#*:}
      t0=$(awk '{print $1}' /proc/uptime)
      if echo | timeout 5 openssl s_client -connect "$ip:$port" -servername "$SNI" >/dev/null 2>&1; then
        t1=$(awk '{print $1}' /proc/uptime)
        awk -v a="$t0" -v b="$t1" -v hp="$hp" 'BEGIN{printf "%d %s OK\n",(b-a)*1000,hp}' >> "$2"
      else
        printf '99999 %s FAIL\n' "$hp" >> "$2"
      fi
    ) &
    N=$((N+1)); [ $((N % 6)) -eq 0 ] && wait
  done < "$1"
  wait
  sort -n "$2" > "$2.sorted"
}

probe "$WORK/hk.hp" "$WORK/hk.res"
probe "$WORK/sg.hp" "$WORK/sg.res"

stat() { # $1=sorted file $2=名字
  f=$1; name=$2
  total=$(wc -l < "$f")
  ok=$(grep -vc '^99999' "$f" 2>/dev/null || echo 0)
  [ "$total" -gt 0 ] || { echo "$name: 无数据"; return; }
  best=$(head -1 "$f" | awk '{print $1}')
  med=$(awk -v n=$(( (ok+1)/2 )) 'NR==n{print $1}' "$f")
  medfail=$(awk -v n=$(( (ok+1)/2 )) 'NR==n && $1==99999 {print "99999"}' "$f")
  top5=$(head -5 "$f" | awk '$1!=99999{printf "%s(%sms) ", $2, $1}')
  echo "== $name：候选 $total，握手成功 $ok"
  echo "   最快 $best ms｜中位(存活) ${medfail:-$med} ms"
  echo "   top5: $top5"
  echo "   全量: $(awk '{printf "%s ", $1}' "$f" | tr -s ' ')"
}
stat "$WORK/hk.res.sorted" "香港池"
stat "$WORK/sg.res.sorted" "新加坡池"

echo
echo "== HK+SG 合并 top8（选拔逻辑模拟：粘性不管，纯延迟+去重后取前8）:"
cat "$WORK/hk.res.sorted" "$WORK/sg.res.sorted" | sort -n | awk '$1!=99999' | head -8 | awk '{printf "   %sms  %s\n", $1, $2}'
