#!/bin/bash
# CleanZip Desktop Launcher (macOS / Linux) - chay truc tiep tu source, khong can build .app
cd "$(dirname "$0")" || exit 1

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "[LOI] Khong tim thay Python 3 tren may!"
    echo "Cai dat qua: brew install python3   (hoac https://www.python.org/)"
    exit 1
fi

# Kiem tra CustomTkinter
if ! "$PYTHON_BIN" -c "import customtkinter" >/dev/null 2>&1; then
    echo "[*] Dang cai dat thu vien giao dien CustomTkinter..."
    "$PYTHON_BIN" -m pip install -r requirements.txt
fi

"$PYTHON_BIN" gui.py
