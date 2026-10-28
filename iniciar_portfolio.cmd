@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Crie o ambiente Python seguindo as instrucoes do README.md.
  pause
  exit /b 1
)
echo Abra http://127.0.0.1:8504 no navegador.
".venv\Scripts\python.exe" -m streamlit run app.py
pause
