import requests

# 查找 LibWrt 的 nss-firmware 版本
urls_to_check = [
    "https://api.github.com/repos/LiBwrt/LibWrt/contents/package/firmware",
    "https://raw.githubusercontent.com/LiBwrt/LibWrt/main/package/firmware/nss-firmware/Makefile",
    "https://raw.githubusercontent.com/LiBwrt-op/openwrt-6.x/main/package/firmware/nss-firmware/Makefile",
]

for url in urls_to_check:
    try:
        r = requests.get(url, timeout=10)
        print(f"\n=== {url} ===")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            content = r.text
            if 'nss' in content.lower():
                for line in content.split('\n'):
                    if 'version' in line.lower() or 'nss' in line.lower() or 'PKG' in line:
                        print(line[:300])
            else:
                print(content[:500])
    except Exception as e:
        print(f"Error: {e}")

# 直接检查 LibWrt 分支
print("\n=== LibWrt 分支 ===")
r = requests.get("https://api.github.com/repos/LiBwrt/LibWrt/branches", timeout=10)
if r.status_code == 200:
    for branch in r.json():
        print(branch['name'])
