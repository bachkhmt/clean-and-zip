#!/bin/bash
# CleanZip Desktop Launcher (macOS / Linux) - chay truc tiep tu source, khong can build .app
cd "$(dirname "$0")" || exit 1

# Xac dinh Python va moi truong venv
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    # Tim Python phu hop co ho tro Tkinter
    CANDIDATES=(
        "/opt/homebrew/bin/python3.12"
        "/opt/homebrew/bin/python3"
        "python3.12"
        "python3.11"
        "python3.10"
        "python3"
        "python"
    )
    FOUND_PY=""
    for cand in "${CANDIDATES[@]}"; do
        if command -v "$cand" >/dev/null 2>&1; then
            if "$cand" -c "import tkinter" >/dev/null 2>&1; then
                FOUND_PY="$cand"
                break
            fi
        fi
    done

    if [ -z "$FOUND_PY" ]; then
        echo "[LOI] Khong tim thay Python 3 co san thu vien Tkinter tren he thong!"
        if [ "$(uname)" = "Darwin" ]; then
            echo "Vui long cai dat qua Homebrew:"
            echo "    brew install python@3.12 python-tk@3.12"
        else
            echo "Vui long cai dat python3-tk (Ubuntu/Debian: sudo apt install python3-tk python3-venv)"
        fi
        exit 1
    fi

    echo "[*] Khoi tao moi truong ao (.venv) tu $FOUND_PY..."
    "$FOUND_PY" -m venv .venv || {
        echo "[LOI] Khong the tao .venv bang $FOUND_PY"
        exit 1
    }
    PYTHON_BIN=".venv/bin/python"
fi

# Kiem tra CustomTkinter, darkdetect & PIL
if ! "$PYTHON_BIN" -c "import customtkinter, darkdetect, PIL" >/dev/null 2>&1; then
    echo "[*] Dang cai dat thu vien giao dien CustomTkinter..."
    "$PYTHON_BIN" -m pip install --upgrade pip >/dev/null 2>&1 || true
    "$PYTHON_BIN" -m pip install -r requirements.txt
fi

exec "$PYTHON_BIN" gui.py
