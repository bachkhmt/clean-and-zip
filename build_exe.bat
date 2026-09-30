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
  --icon "public/cleanzip.ico" ^
  --add-data "default-excludes.txt;." ^
  --add-data "public;public" ^
  --collect-all customtkinter ^
  --collect-all PIL ^
  gui.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo [+] THANH CONG! File .exe da duoc tao trong thu muc 'dist':
    echo     dist\CleanZip.exe
    echo ========================================================
    
    :: Tao shortcut ra Desktop
    powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'CleanZip.lnk')); $s.TargetPath = [System.IO.Path]::GetFullPath('dist\CleanZip.exe'); $s.WorkingDirectory = [System.IO.Path]::GetFullPath('dist'); $s.IconLocation = [System.IO.Path]::GetFullPath('public\cleanzip.ico'); $s.Description = 'CleanZip - Cong cu dong goi du an sach se'; $s.Save()"
    echo [+] Da tao / cap nhat shortcut CleanZip tren man hinh Desktop!
) else (
    echo.
    echo [-] Build that bai, vui long kiem tra lai thong bao loi o tren.
)

pause
