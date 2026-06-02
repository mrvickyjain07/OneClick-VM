import requests

# Try different Kali URL patterns
urls = [
    "https://cdimage.kali.org/kali-2024.4/kali-linux-2024.4-live-amd64.iso",
    "https://cdimage.kali.org/current/kali-linux-2024.4-live-amd64.iso",
    "https://kali.download/base-images/kali-2024.4/kali-linux-2024.4-live-amd64.iso",
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
