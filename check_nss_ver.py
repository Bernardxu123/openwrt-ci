import requests

# 检查 breeze303/openwrt-ci 的 nss-packages
urls = [
    "https://raw.githubusercontent.com/breeze303/openwrt-ci/main/feeds.conf",
    "https://api.github.com/repos/breeze303/openwrt-ci/contents/package",
    "https://raw.githubusercontent.com/breeze303/openwrt-ci/main/configs/ipq60xx-all.config",
]

for url in urls:
    try:
        r = requests.get(url, timeout=10)
        print(f"\n=== {url} ===")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            content = r.text
            for line in content.split('\n'):
                if 'nss' in line.lower() or 'wifi' in line.lower():
                    print(line[:300])
    except Exception as e:
        print(f"Error: {e}")
