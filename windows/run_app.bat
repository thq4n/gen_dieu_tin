@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\streamlit.exe" (
  echo Chua cai dat. Chay setup.bat truoc.
  echo.
  pause
  exit /b 1
)

echo Mo trinh duyet tai http://localhost:8501 (Streamlit tu mo neu duoc).
echo Dong cua so nay hoac Ctrl+C de thoat.
echo.
".venv\Scripts\streamlit.exe" run streamlit_app.py

pause
