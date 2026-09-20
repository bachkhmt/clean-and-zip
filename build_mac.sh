#!/bin/bash
# CleanZip - Dong goi ung dung Desktop (.app) bang PyInstaller (macOS / Linux)
cd "$(dirname "$0")" || exit 1

echo "========================================================"
echo "  DONG GOI CLEANZIP THANH DESKTOP APP BANG PYINSTALLER"
echo "========================================================"
echo ""

# Xac dinh lenh python (uu tien python3, macOS hien dai khong con python mac dinh)
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "[LOI] Khong tim thay Python 3 tren may!"
    echo "Cai dat qua: brew install python3   (hoac tai tai https://www.python.org/)"
    exit 1
fi

# Kiem tra PyInstaller
if ! "$PYTHON_BIN" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "[*] Dang cai dat PyInstaller..."
    "$PYTHON_BIN" -m pip install pyinstaller
fi

echo "[*] Dang tien hanh build..."
# Luu y: tren macOS/Linux, dau phan cach cua --add-data la dau ":" (Windows dung ";")
if "$PYTHON_BIN" -m PyInstaller --noconfirm --windowed --onefile \
    --name "CleanZip" \
    --add-data "default-excludes.txt:." \
    --collect-all customtkinter \
    gui.py; then

    echo ""
    echo "========================================================"
    if [ "$(uname)" = "Darwin" ]; then
        echo "[+] THANH CONG! Ung dung da duoc tao:"
        echo "    dist/CleanZip.app"
        echo ""
        echo "[!] App chua duoc ky (code sign) nen macOS Gatekeeper co the chan"
        echo "    lan mo dau tien voi thong bao 'khong xac dinh duoc nha phat trien'."
        echo "    Cach 1: Chuot phai (hoac Ctrl+click) vao CleanZip.app -> chon Open -> Open."
        echo "    Cach 2: Chay lenh sau roi mo lai binh thuong:"
        echo "        xattr -cr dist/CleanZip.app"
    else
        echo "[+] THANH CONG! File thuc thi da duoc tao:"
        echo "    dist/CleanZip"
        echo "    (co the can chmod +x dist/CleanZip truoc khi chay)"
    fi
    echo "========================================================"
else
    echo ""
    echo "[-] Build that bai, vui long kiem tra lai thong bao loi o tren."
    exit 1
fi
