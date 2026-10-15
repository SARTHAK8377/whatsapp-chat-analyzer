@echo off
rem Double-click to open the WhatsApp Chat Analyzer in your browser.
rem Close this window to stop the app.
cd /d "%~dp0"
py -3.12 whatsapp_analyzer.py
if errorlevel 1 pause
