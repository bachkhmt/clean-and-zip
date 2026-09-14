@echo off
title CleanZip Desktop Launcher
cd /d "%~dp0"

:: Kiem tra Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python tren may tinh!
    echo Vui long cai dat Python va them vao PATH: https://www.python.org/
    pause
    exit /b 1
)

:: Kiem tra CustomTkinter
python -c "import customtkinter" >nul 2>nul
if %errorlevel% neq 0 (
    echo [*] Dang cai dat thu vien giao dien CustomTkinter...
    pip install -r requirements.txt
)

:: Khoi chay bang pythonw de khong bi hien cua so console den
start "" pythonw gui.py
if %errorlevel% neq 0 (
    :: Fallback sang python thuong neu pythonw co van de
    python gui.py
)
exit
