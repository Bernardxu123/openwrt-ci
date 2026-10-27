import json
import sys
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://192.168.31.1:2023/graphql"

def post(body, tok=None):
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["Authorization"] = tok
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers=headers)
    r = json.load(urllib.request.urlopen(req, timeout=30))
    if r.get("errors"):
        print("ERRORS:", r["errors"])
    return r.get("data")

tok = post({"query": '{ token(username:"root", password:"Qazswxdecf1") }'})["token"]
data = post({"query": """{
  nodeLatencies {
    id
    latencyMs
    alive
    message
  }
  groups {
    name
    policy
    nodes {
      id
      name
      protocol
    }
  }
}"""}, tok)

lat_map = {l["id"]: l for l in data["nodeLatencies"]}

for g in data["groups"]:
    print(f"\nGroup: {g['name']} (policy={g['policy']}, nodes={len(g['nodes'])})")
    for n in g["nodes"]:
        lat = lat_map.get(n["id"], {})
        status = "ALIVE" if lat.get("alive") else f"DEAD ({lat.get('message')})"
        print(f"  {n['name']} [{n['protocol']}]: {lat.get('latencyMs')}ms - {status}")
