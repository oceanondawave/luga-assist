# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None
base_dir = Path.cwd()

datas = [
    (str(base_dir / "web"), "web"),
    (str(base_dir / "temp"), "temp"),
]

hiddenimports = [
    "sounddevice",
    "speech_recognition",
    "pynput",
    "pynput.keyboard",
    "pynput.mouse",
    "pystray",
    "pyautogui",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "edge_tts",
    "gtts",
    "fastapi",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "websockets",
    "gemini_webapi",
    "audioop",
    "AppKit",
    "ApplicationServices",
    "pyperclip",
    "mss",
    "loguru",
]

a = Analysis(
    ['app/main.py'],
    pathex=[str(base_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Luga Assist',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Luga Assist',
)

app = BUNDLE(
    coll,
    name='Luga Assist.app',
    icon=None,
    bundle_identifier='com.luga.assist',
    info_plist={
        'CFBundleName': 'Luga Assist',
        'CFBundleDisplayName': 'Luga Assist',
        'CFBundleIdentifier': 'com.luga.assist',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSMicrophoneUsageDescription': 'Luga Assist cần quyền truy cập Micro để nhận diện câu lệnh giọng nói.',
        'NSSpeechRecognitionUsageDescription': 'Luga Assist cần quyền nhận diện giọng nói.',
        'NSAppleEventsUsageDescription': 'Luga Assist cần quyền điều khiển hệ thống qua AppleScript.',
        'NSAccessibilityUsageDescription': 'Luga Assist cần quyền trợ năng để hỗ trợ điều khiển máy tính.',
        'NSScreenCaptureUsageDescription': 'Luga Assist cần quyền chụp màn hình để AI quan sát giao diện.',
    },
)
