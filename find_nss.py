import requests

# 检查 LiBwrt nss 包的实际位置
urls = [
    "https://api.github.com/repos/LiBwrt/LibWrt/contents/package/firmware?ref=25.12-nss",
    "https://api.github.com/repos/LiBwrt/LibWrt/contents/package/firmware?ref=main-nss",
    "https://api.github.com/search/code?q=repo:LiBwrt/LibWrt+nss-firmware+extension:mk",
]

for url in urls:
    try:
        r = requests.get(url, timeout=10)
        print(f"\n=== {url[:60]} ===")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                for item in data[:15]:
                    name = item.get('name', '')
                    if 'nss' in name.lower() or 'wifi' in name.lower() or 'qca' in name.lower():
                        print(f"  {name} -> {item.get('path', '')[:100]}")
            elif isinstance(data, dict) and 'items' in data:
                for item in data['items'][:15]:
                    print(f"  {item.get('name', '')} -> {item.get('path', '')[:100]}")
            elif isinstance(data, dict):
                for item in data.get('tree', [])[:15]:
                    path = item.get('path', '')
                    if 'nss' in path.lower() or 'qca' in path.lower():
                        print(f"  {path}")
    except Exception as e:
        print(f"Error: {e}")
