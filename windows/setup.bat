@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo === Gen Dieu Tin - cai dat lan dau (Windows) ===
echo.

set "CREATED=0"
if exist ".venv\Scripts\python.exe" goto pip

echo Tao moi truong ao .venv ...
py -3 -m venv .venv 2>nul
if not errorlevel 1 set "CREATED=1"
if "%CREATED%"=="0" (
  python -m venv .venv 2>nul
  if not errorlevel 1 set "CREATED=1"
)
if "%CREATED%"=="0" (
  echo.
  echo [LOI] Khong tao duoc venv. Hay cai Python 3.10+ tu https://www.python.org/downloads/
  echo        Khi cai: tich "Add python.exe to PATH". Sau do chay lai setup.bat
  echo.
  pause
  exit /b 1
)

:pip
echo Cap nhat pip va cai packages (co the vai phut) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto pipfail
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 goto pipfail

echo.
echo === Xong. Chay run_app.bat de mo ung dung. ===
echo.
pause
exit /b 0

:pipfail
echo.
echo [LOI] pip install that bai. Kiem tra mang / firewall / proxy.
echo.
pause
exit /b 1
