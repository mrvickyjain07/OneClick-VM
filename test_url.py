import requests

urls = [
    "https://releases.ubuntu.com/24.04/ubuntu-24.04.1-desktop-amd64.iso",
    "https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/39/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-39-1.5.iso",
    "https://mirror.math.princeton.edu/pub/ubuntu-iso/24.04/ubuntu-24.04.1-desktop-amd64.iso"
]

for url in urls:
    try:
        r = requests.head(url, allow_redirects=True, timeout=5)
        print(f"{r.status_code} - {url}")
    except Exception as e:
        print(f"ERROR - {url} : {e}")
