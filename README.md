# Morsoul Game Launcher Client

Distributable desktop launcher client for **Morsoul: World's Case**, built with PySide6 (Qt) and Python.

---

## Features
- **Modern Dark Fantasy UI**: Custom themed frames, authentication modal with back navigation, tabs for Home and Profile/Account management.
- **Dynamic Server Discovery**: Automatically reads `server.json` or fetches the latest server endpoint from a remote GitHub raw URL (`SERVER_CONFIG_URL`), allowing seamless connection to Cloudflare Tunnels without distributing new client builds.
- **Save Synchronization**: Bidirectional save sync with conflict detection between local encrypted SQLite saves and cloud MongoDB snapshots.
- **Tamper Evidence**: Cryptographic HMAC verification for game saves and Ed25519 signature checks for game patches.
- **Game Process Lock**: Automatically monitors running game processes to prevent concurrent save corruption.

---

## Directory Structure
```
morsoul-client/
├── morsoul_core/           # Shared models, HMAC integrity, savestore, and paths
├── morsoul_launcher/       # Launcher controller, API client, sync engine, updater
├── morsoul_launcher_ui/    # PySide6 desktop UI screens, theme, and image assets
├── tests/                  # Client and launcher unit tests
├── dist/                   # Built standalone executable (MorsoulLauncher.exe)
├── build_exe.bat           # PyInstaller build script
├── run_launcher.bat        # Launch from source in virtualenv
├── launcher_main.py        # Entry point for PyInstaller build
├── MorsoulLauncher.spec    # PyInstaller specification file
├── server.json             # Local fallback server endpoint
├── .env.example            # Environment configuration template
└── pyproject.toml          # Client package configuration and dependencies
```

---

## Quick Start (Running from Source)

### 1. Prerequisites
- Python 3.11+
- Recommended: [uv](https://docs.astral.sh/uv/) or standard `venv`

### 2. Setup Virtual Environment
```powershell
uv venv .venv
.\.venv\Scripts\activate
uv pip install -e .
```
Or using standard pip:
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

### 3. Configuration
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Fill in the values:
- `SAVE_HMAC_KEY`: 32-byte base64 HMAC key (must match backend).
- `SERVER_CONFIG_URL`: (Optional) Raw GitHub URL to your `server.json` file.
- `DEFAULT_SERVER_URL`: URL to your server (e.g. `http://127.0.0.1:8080` or Cloudflare tunnel URL).

### 4. Run Launcher
Double-click `run_launcher.bat` or run:
```powershell
python -m morsoul_launcher_ui
```

---

## Building the Standalone Executable
To package the launcher into a single executable without requiring Python on end-user machines:

```powershell
.\build_exe.bat
```
The compiled binary will be placed in `dist/MorsoulLauncher.exe`. Ship `dist/MorsoulLauncher.exe` along with `server.json` (or set `SERVER_CONFIG_URL` in `.env`).

---

## Running Tests
```powershell
pytest tests/ -v
```
