import requests

urls = [
    "https://releases.ubuntu.com/24.04.1/ubuntu-24.04.1-desktop-amd64.iso",
    "https://cdimage.kali.org/kali-2024.4/kali-linux-2024.4-live-amd64.iso"
]

for url in urls:
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        print(f"✓ {url}")
        print(f"  Status: {response.status_code}")
        print(f"  Size: {int(response.headers.get('content-length', 0)) / 1024 / 1024:.1f} MB")
    except Exception as e:
        print(f"✗ {url}")
        print(f"  Error: {e}")
    print()
