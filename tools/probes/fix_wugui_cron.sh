#!/bin/sh
# 把 wugui crontab 从 50 5 换成 8 */6
if grep -q 'wugui-sub-update' /etc/crontabs/root; then
  grep -v 'wugui-sub-update' /etc/crontabs/root > /etc/crontabs/root.tmp
  mv /etc/crontabs/root.tmp /etc/crontabs/root
fi
echo '8 */6 * * * /usr/bin/wugui-sub-update.sh # wugui-sub-update' >> /etc/crontabs/root
/etc/init.d/cron restart >/dev/null 2>&1
echo "=== crontab now ==="
grep wugui /etc/crontabs/root
