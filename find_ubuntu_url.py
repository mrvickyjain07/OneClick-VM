import requests

# Try different Ubuntu URL patterns
urls = [
    "https://releases.ubuntu.com/24.04/ubuntu-24.04-desktop-amd64.iso",
    "https://releases.ubuntu.com/24.04.1/ubuntu-24.04.1-desktop-amd64.iso",
    "https://releases.ubuntu.com/noble/ubuntu-24.04-desktop-amd64.iso",
]

for url in urls:
    try:
        print(f"Trying: {url}")
        response = requests.head(url, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            print(f"  ✓ Status: {response.status_code}")
            print(f"  Size: {int(response.headers.get('content-length', 0)) / 1024 / 1024:.1f} MB")
            print(f"  WORKING URL!")
            break
        else:
            print(f"  ✗ Status: {response.status_code}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    print()
