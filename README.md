# OneClick VM

A cross-platform desktop application to deploy VMs in one click using VirtualBox.

## Features
- **One-Click Deploy**: Download ISO, create VM, and launch automatically.
- **Smart Caching**: Resumable downloads and ISO caching to avoid re-downloading.
- **Dashboard**: Manage created VMs (Start, Stop, Delete).

## Prerequisites
- **VirtualBox**: Must be installed and reachable via `VBoxManage` (add to system PATH).
- **Python 3.8+**

## Installation

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### GUI Mode
Run the desktop application:
```bash
python frontend/app.py
```

### CLI Mode (Test)
Run the backend installer in the terminal:
```bash
python main.py
```

## Structure
- `backend/`: Core logic (ISO manager, VBox engine, etc.)
- `frontend/`: PyQt5 UI code.
- `templates/`: VM configuration templates (JSON).
- `cache/`: Stores downloaded ISOs and VM registry.

## Troubleshooting
- **VirtualBox not found**: Ensure `VBoxManage` is in your environment PATH.
- **Download fails**: Check internet connection. The app supports resuming downloads.
