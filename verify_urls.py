import requests

print("Testing URLs...\n")

# Test Ubuntu
ubuntu_urls = [
    "https://releases.ubuntu.com/24.04/ubuntu-24.04-desktop-amd64.iso",
    "https://mirror.kku.ac.th/ubuntu-releases/24.04/ubuntu-24.04-desktop-amd64.iso",
]

debian_urls = [
    "https://cdimage.debian.org/debian-cd/current-live/amd64/iso-hybrid/debian-live-12.8.0-amd64-xfce.iso",
]

print("=== Ubuntu 24.04 Desktop ===")
for url in ubuntu_urls:
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True)
        if resp.status_code == 200:
            size_mb = int(resp.headers.get('content-length', 0)) / 1024 / 1024
            print(f"✓ {url}")
            print(f"  Size: {size_mb:.1f} MB")
            break
        else:
            print(f"✗ {url} - Status: {resp.status_code}")
    except Exception as e:
        print(f"✗ {url} - Error: {str(e)[:50]}")

print("\n=== Debian 12 Live ===")
for url in debian_urls:
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True)
        if resp.status_code == 200:
            size_mb = int(resp.headers.get('content-length', 0)) / 1024 / 1024
            print(f"✓ {url}")
            print(f"  Size: {size_mb:.1f} MB")
        else:
            print(f"✗ {url} - Status: {resp.status_code}")
    except Exception as e:
        print(f"✗ {url} - Error: {str(e)[:50]}")
