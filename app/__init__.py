"""
Luga Assist - AI Desktop Assistant for Visually Impaired Users.
"""
import sys
import os
import io

__version__ = "1.0.0"

# Guard against PyInstaller windowless mode (console=False) setting stdout/stderr to None
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        sys.stdout = io.StringIO()

if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        sys.stderr = io.StringIO()
