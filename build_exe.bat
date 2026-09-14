@echo off
title CleanZip - Dong goi ung dung Desktop (.exe)
cd /d "%~dp0"

echo ========================================================
echo   DONG GOI CLEANZIP THANH DESKTOP APP (.EXE) BANG PYINSTALLER
echo ========================================================
echo.

:: Kiem tra PyInstaller
python -c "import PyInstaller" >nul 2>nul
if %errorlevel% neq 0 (
    echo [*] Dang cai dat PyInstaller...
    pip install pyinstaller
)

echo [*] Dang tien hanh build file .exe...
pyinstaller --noconfirm --windowed --onefile ^
  --name "CleanZip" ^
  --add-data "default-excludes.txt;." ^
  --collect-all customtkinter ^
  gui.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo [+] THANH CONG! File .exe da duoc tao trong thu muc 'dist':
    echo     dist\CleanZip.exe
    echo ========================================================
) else (
    echo.
    echo [-] Build that bai, vui long kiem tra lai thong bao loi o tren.
)

pause
