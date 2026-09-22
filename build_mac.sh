#!/bin/bash
# CleanZip - Dong goi ung dung Desktop (.app) bang PyInstaller (macOS / Linux)
cd "$(dirname "$0")" || exit 1

echo "========================================================"
echo "  DONG GOI CLEANZIP THANH DESKTOP APP BANG PYINSTALLER"
echo "========================================================"
echo ""

# Xac dinh Python va moi truong venv
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    # Tim Python phu hop co ho tro Tkinter (uu tien Python 3.12/3.11 Homebrew hoac he thong)
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

# Kiem tra & cai dat dependencies (customtkinter, darkdetect, Pillow, pyinstaller)
if ! "$PYTHON_BIN" -c "import customtkinter, darkdetect, PIL, PyInstaller" >/dev/null 2>&1; then
    echo "[*] Dang cai dat dependencies can thiet (requirements.txt + pyinstaller)..."
    "$PYTHON_BIN" -m pip install --upgrade pip >/dev/null 2>&1 || true
    "$PYTHON_BIN" -m pip install -r requirements.txt pyinstaller
fi

# Tao icon .icns chuan tren macOS neu chua co
ICON_ARG=""
if [ "$(uname)" = "Darwin" ]; then
    if [ ! -f "public/cleanzip.icns" ] && [ -f "public/cleanzip_square.png" ] && command -v iconutil >/dev/null 2>&1 && command -v sips >/dev/null 2>&1; then
        echo "[*] Dang tao icon chuan .icns cho macOS tu public/cleanzip_square.png..."
        ICONSET_DIR="/tmp/cleanzip.iconset"
        rm -rf "$ICONSET_DIR"
        mkdir -p "$ICONSET_DIR"
        sips -z 16 16 public/cleanzip_square.png --out "$ICONSET_DIR/icon_16x16.png" >/dev/null 2>&1
        sips -z 32 32 public/cleanzip_square.png --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1
        sips -z 32 32 public/cleanzip_square.png --out "$ICONSET_DIR/icon_32x32.png" >/dev/null 2>&1
        sips -z 64 64 public/cleanzip_square.png --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1
        sips -z 128 128 public/cleanzip_square.png --out "$ICONSET_DIR/icon_128x128.png" >/dev/null 2>&1
        sips -z 256 256 public/cleanzip_square.png --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1
        sips -z 256 256 public/cleanzip_square.png --out "$ICONSET_DIR/icon_256x256.png" >/dev/null 2>&1
        sips -z 512 512 public/cleanzip_square.png --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1
        sips -z 512 512 public/cleanzip_square.png --out "$ICONSET_DIR/icon_512x512.png" >/dev/null 2>&1
        iconutil -c icns "$ICONSET_DIR" -o public/cleanzip.icns >/dev/null 2>&1
        rm -rf "$ICONSET_DIR"
    fi

    if [ -f "public/cleanzip.icns" ]; then
        ICON_ARG="public/cleanzip.icns"
    elif [ -f "public/cleanzip.ico" ]; then
        ICON_ARG="public/cleanzip.ico"
    fi
else
    if [ -f "public/cleanzip.ico" ]; then
        ICON_ARG="public/cleanzip.ico"
    fi
fi

echo "[*] Dang tien hanh dong goi..."
BUILD_FLAGS=(
    --noconfirm
    --windowed
    --name "CleanZip"
    --add-data "default-excludes.txt:."
    --add-data "public:public"
    --collect-all customtkinter
    --collect-all PIL
)

if [ -n "$ICON_ARG" ]; then
    BUILD_FLAGS+=(--icon "$ICON_ARG")
fi

if [ "$(uname)" != "Darwin" ]; then
    BUILD_FLAGS=(--onefile "${BUILD_FLAGS[@]}")
fi

BUILD_FLAGS+=("gui.py")

if "$PYTHON_BIN" -m PyInstaller "${BUILD_FLAGS[@]}"; then
    echo ""
    echo "========================================================"
    if [ "$(uname)" = "Darwin" ]; then
        # Go bo quarantine flag de tranh loi Gatekeeper tren may build
        xattr -cr dist/CleanZip.app 2>/dev/null || true

        # Tao shortcut tai Desktop cho nguoi dung
        SHORTCUT_PATH="$HOME/Desktop/CleanZip.app"
        CURRENT_DIR="$(pwd)"
        ln -sfn "$CURRENT_DIR/dist/CleanZip.app" "$SHORTCUT_PATH" 2>/dev/null || true

        echo "[+] THANH CONG! Ung dung macOS da duoc tao:"
        echo "    dist/CleanZip.app"
        echo ""
        echo "[+] Da tao shortcut ung dung tai Desktop:"
        echo "    $SHORTCUT_PATH"
        echo ""
        echo "[*] Ban co the mo truc tiep tu Desktop hoac bang lenh:"
        echo "    open dist/CleanZip.app"
        echo "    (hoac keo vao thu muc /Applications de su dung)"
    else
        chmod +x dist/CleanZip 2>/dev/null || true
        echo "[+] THANH CONG! File thuc thi da duoc tao:"
        echo "    dist/CleanZip"
    fi
    echo "========================================================"
else
    echo ""
    echo "[-] Build that bai, vui long kiem tra lai thong bao loi o tren."
    exit 1
fi
