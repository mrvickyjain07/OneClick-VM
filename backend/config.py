import os
import pathlib
import sys
import json
import sys

# Define base paths
if getattr(sys, 'frozen', False):
    BASE_DIR = pathlib.Path(sys.executable).parent
else:
    BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

# Directories
TEMPLATE_DIR      = BASE_DIR / "templates"
CACHE_DIR         = BASE_DIR / "cache"
ISO_CACHE_DIR     = CACHE_DIR / "isos"           # marketplace download cache
ISO_LIBRARY_DIR   = CACHE_DIR / "iso_library"    # manually managed ISOs
ISO_DB_PATH       = CACHE_DIR / "isos.json"      # ISO manager metadata DB
SNAPSHOT_DB_PATH  = CACHE_DIR / "snapshots.json" # snapshot metadata DB
VM_REPO_PATH      = CACHE_DIR / "vms.json"       # UUID-keyed VMRepository (new)
LOG_DIR           = BASE_DIR  / "logs"
VM_REGISTRY_PATH  = CACHE_DIR / "vm_registry.json"
VM_DATA_DIR       = BASE_DIR  / "vm_data"
APP_SETTINGS_PATH = CACHE_DIR / "settings.json"

def load_config() -> dict:
    # Environment variables take highest priority, then settings.json
    cfg = {}
    if APP_SETTINGS_PATH.exists():
        try:
            with open(APP_SETTINGS_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    # Env var overrides (CI / advanced deployment)
    if os.environ.get("ONECLICK_VM_DIR"):
        cfg["vm_data_dir"] = os.environ["ONECLICK_VM_DIR"]
    if os.environ.get("ONECLICK_ISO_DIR"):
        cfg["iso_cache_dir"] = os.environ["ONECLICK_ISO_DIR"]
    return cfg

def save_config(data: dict):
    with open(APP_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def ensure_directories():
    """Ensure all required directories exist and initialize variables from config."""
    global VM_DATA_DIR, ISO_CACHE_DIR
    
    # Load user-configured paths if any exist
    c = load_config()
    if c.get("vm_data_dir"):
        VM_DATA_DIR = pathlib.Path(c["vm_data_dir"])
    if c.get("iso_cache_dir"):
        ISO_CACHE_DIR = pathlib.Path(c["iso_cache_dir"])

    dirs = [TEMPLATE_DIR, ISO_CACHE_DIR, ISO_LIBRARY_DIR, LOG_DIR, VM_DATA_DIR]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

# Call on import or explicitly? Explicit is better, but config often runs at start.
# We'll rely on main/app to call ensure_directories
