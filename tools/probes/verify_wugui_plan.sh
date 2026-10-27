#!/bin/sh
printf '{"query":"query($u:String!,$p:String!){ token(username:$u,password:$p) }","variables":{"u":"root","p":"Qazswxdecf1"}}' > /tmp/dd-tok.json
TOKEN=$(curl -s -X POST http://192.168.31.1:2023/graphql -H 'Content-Type: application/json' --data-binary @/tmp/dd-tok.json | jsonfilter -e '@.data.token')
printf '%s' '{"query":"{ subscriptions { id tag cronExp cronEnable updatedAt nodes { totalCount } } }"}' > /tmp/dd-q.json
curl -s -X POST http://192.168.31.1:2023/graphql -H 'Content-Type: application/json' -H "Authorization: $TOKEN" --data-binary @/tmp/dd-q.json
echo
echo "=== crontab ==="
grep wugui /etc/crontabs/root
