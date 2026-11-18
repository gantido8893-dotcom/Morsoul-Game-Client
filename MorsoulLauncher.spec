# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path.cwd()

# Collect dependencies that use dynamic loading or entry points
sqlcipher_datas, sqlcipher_binaries, sqlcipher_hidden = collect_all("sqlcipher3")
keyring_datas, keyring_binaries, keyring_hidden = collect_all("keyring")
cryptography_datas, cryptography_binaries, cryptography_hidden = collect_all("cryptography")

datas = [
    (str(ROOT / "morsoul_launcher_ui" / "assets"), "morsoul_launcher_ui/assets"),
]
if (ROOT / ".env").exists():
    datas.append((str(ROOT / ".env"), "."))
if (ROOT / ".env.client").exists():
    datas.append((str(ROOT / ".env.client"), "."))
if (ROOT / "server.json").exists():
    datas.append((str(ROOT / "server.json"), "."))

datas += sqlcipher_datas + keyring_datas + cryptography_datas
binaries = sqlcipher_binaries + keyring_binaries + cryptography_binaries
hiddenimports = [
    "sqlcipher3",
    "sqlcipher3.dbapi2",
    "keyring",
    "keyring.backends",
    "keyring.backends.Windows",
    "cryptography",
    "pydantic",
    "pydantic_settings",
    "platformdirs",
    "aiohttp",
    "httpx",
    "watchdog",
    "morsoul_core",
    "morsoul_core.paths",
    "morsoul_core.savestore",
    "morsoul_launcher",
    "morsoul_launcher.profile_service",
    "morsoul_launcher.controller",
    "morsoul_launcher.api",
    "morsoul_launcher.config",
    "morsoul_launcher.tokens",
    "morsoul_launcher.appstate",
    "morsoul_launcher_ui",
    "morsoul_launcher_ui.app",
    "morsoul_launcher_ui.bridge",
    "morsoul_launcher_ui.main_window",
    "morsoul_launcher_ui.theme",
    "morsoul_launcher_ui.screens.home",
    "morsoul_launcher_ui.screens.account",
    "morsoul_launcher_ui.screens.auth_modal",
    "morsoul_launcher_ui.screens.delete_account_modal",
    "morsoul_launcher_ui.screens.forgot_password_modal",
    "morsoul_launcher_ui.screens.offline_modal",
    "morsoul_launcher_ui.screens.progress",
    "morsoul_launcher_ui.screens.sign_out_all_modal",
    "morsoul_launcher_ui.toast",
] + sqlcipher_hidden + keyring_hidden + cryptography_hidden

icon_path = str(ROOT / "morsoul_launcher_ui" / "assets" / "game_icon.ico")
if not Path(icon_path).exists():
    icon_path = None

a = Analysis(
    ["launcher_main.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MorsoulLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

