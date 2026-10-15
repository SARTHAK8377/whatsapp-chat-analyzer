@echo off
rem Double-click to open the WhatsApp Chat Analyzer in your browser.
rem Close this window to stop the app.
cd /d "%~dp0"
py -3 -c "import streamlit, pandas, plotly, emoji, regex, scipy" 2>nul || (
  echo Installing what the app needs. This only happens the first time and takes a few minutes...
  py -3 -m pip install -r requirements.txt || goto :error
)
py -3 whatsapp_analyzer.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Something went wrong. Is Python 3.10 or newer installed from python.org?
pause
