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

<img width="1919" height="1140" alt="Screenshot 2026-04-28 081327" src="https://github.com/user-attachments/assets/6005a35c-6079-449f-9a1f-fec1d8b96253" />
<img width="1919" height="1142" alt="Screenshot 2026-04-28 081341" src="https://github.com/user-attachments/assets/b4508991-b963-49a2-b9be-ad361ed3d125" />
<img width="1919" height="1139" alt="Screenshot 2026-04-28 081420" src="https://github.com/user-attachments/assets/67081e10-5f71-4ea2-af07-33522eda403a" />
<img width="1911" height="1145" alt="Screenshot 2026-04-28 081713" src="https://github.com/user-attachments/assets/48e1c4b2-2f4a-480d-893f-6d93a9ad5751" />
<img width="1919" height="1135" alt="Screenshot 2026-04-28 081506" src="https://github.com/user-attachments/assets/da3361f6-3ff0-44b0-8380-e680bedc40a6" />
<img width="1919" height="1137" alt="Screenshot 2026-04-28 081457" src="https://github.com/user-attachments/assets/29dd0ffa-f9e9-4258-9c3c-2ce0f774f1ee" />
<img width="1919" height="1137" alt="Screenshot 2026-04-28 081446" src="https://github.com/user-attachments/assets/85f28203-b121-4262-acfb-2dfdcf9c9694" />
<img width="1919" height="1137" alt="Screenshot 2026-04-28 081432" src="https://github.com/user-attachments/assets/fac90dd0-a51c-4905-808b-e3954a5d755f" />

