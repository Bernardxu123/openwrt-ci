import requests

# 检查 LibWrt 的 nss 分支中的固件版本
urls = [
    "https://raw.githubusercontent.com/LiBwrt/LibWrt/25.12-nss/package/firmware/nss-firmware/Makefile",
    "https://raw.githubusercontent.com/LiBwrt/LibWrt/25.12-nss/package/nss/qca-nss-drv/Makefile",
    "https://raw.githubusercontent.com/LiBwrt/LibWrt/main-nss/package/firmware/nss-firmware/Makefile",
    "https://api.github.com/repos/LiBwrt/LibWrt/contents/package/firmware/nss-firmware?ref=25.12-nss",
]

for url in urls:
    try:
        r = requests.get(url, timeout=10)
        print(f"\n=== {url} ===")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            content = r.text
            if 'version' in content.lower() or 'PKG' in content or 'ver' in content.lower()[:500]:
                for line in content.split('\n')[:30]:
                    if 'ver' in line.lower() or 'PKG' in line or 'name' in line.lower():
                        print(line[:300])
            else:
                print(content[:500])
    except Exception as e:
        print(f"Error: {e}")
