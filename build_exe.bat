@echo off
rem Builds "Chat Analyzer.exe" into your Downloads folder. Takes a few minutes.
cd /d "%~dp0"
py -3.12 -m PyInstaller --noconfirm --clean --onefile --name "Chat Analyzer" ^
  --distpath "%USERPROFILE%\Downloads" --workpath "%TEMP%\chat_analyzer_build" --specpath "%TEMP%\chat_analyzer_build" ^
  --add-data "%~dp0whatsapp_analyzer.py;." ^
  --collect-all streamlit --copy-metadata streamlit ^
  --collect-data plotly --collect-data emoji ^
  exe_launcher.py
if errorlevel 1 pause
