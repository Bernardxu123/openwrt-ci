#!/usr/bin/env python3
"""从 PC 经路由器拉 YouTube 视频流复现播放中断；配合 daed debug 日志定位。"""
import json
import subprocess
import time
import urllib.request

VIDEO = "jNQXAC9IVRw"
KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
body = {
    "context": {"client": {"clientName": "ANDROID", "clientVersion": "20.10.38",
                            "androidSdkVersion": 30}},
    "videoId": VIDEO,
    "contentCheckOk": True,
    "racyCheckOk": True,
}
req = urllib.request.Request(
    "https://www.youtube.com/youtubei/v1/player?key=%s&prettyPrint=false" % KEY,
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "User-Agent": "com.google.android.youtube/20.10.38"})
data = json.load(urllib.request.urlopen(req, timeout=20))
fmts = data.get("streamingData", {}).get("adaptiveFormats") or []
print("拿到 %d 个流" % len(fmts))
if not fmts:
    print(json.dumps(data, ensure_ascii=False)[:400])
    raise SystemExit("没有流")

# 选一个 18 号格式附近的混合流（有音频视频的 muxed），或最大的 progressive
prog = [f for f in fmts if f.get("url")]
prog.sort(key=lambda f: f.get("bitrate", 0), reverse=True)
if not prog:
    raise SystemExit("没有带 url 的流")
f = prog[0]
print("用格式 itag=%s bitrate=%s mime=%s" % (f.get("itag"), f.get("bitrate"), f.get("mimeType", "")[:40]))
url = f["url"].split("\\u0026")[0].replace("\\u0026", "&")

print("开始拉流 150 秒，观察中断……")
t0 = time.time()
p = subprocess.Popen(["curl", "-s", "-o", "NUL", "-m", "150", "-w",
                      "code=%{http_code} time=%{time_total}s size=%{size_download}", url],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
out = p.communicate()[0].decode()
print("curl 结果:", out, "| 墙钟 %.0fs" % (time.time() - t0))
