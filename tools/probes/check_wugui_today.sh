#!/bin/sh
echo "=== date ==="
date
echo "=== wugui log ==="
cat /tmp/wugui-sub-update.log 2>/dev/null
echo "=== crontab ==="
grep -n wugui /etc/crontabs/root 2>/dev/null
echo "=== daed 乌龟 ==="
printf '{"query":"query($u:String!,$p:String!){ token(username:$u,password:$p) }","variables":{"u":"root","p":"Qazswxdecf1"}}' > /tmp/dd-tok.json
TOKEN=$(curl -s --connect-timeout 5 --max-time 15 -X POST http://192.168.31.1:2023/graphql -H 'Content-Type: application/json' --data-binary @/tmp/dd-tok.json | jsonfilter -e '@.data.token')
printf '%s' '{"query":"{ subscriptions { id tag link cronExp cronEnable updatedAt nodes { totalCount } } }"}' > /tmp/dd-s.json
curl -s --connect-timeout 5 --max-time 15 -X POST http://192.168.31.1:2023/graphql -H 'Content-Type: application/json' -H "Authorization: $TOKEN" --data-binary @/tmp/dd-s.json
echo
echo "=== conf API ==="
grep WUGUI_API /etc/wugui-sub.conf
