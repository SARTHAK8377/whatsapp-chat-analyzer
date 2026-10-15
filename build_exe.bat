@echo off
rem Builds "Chat Analyzer.exe" into your Downloads folder. Takes about 20 minutes.
cd /d "%~dp0"
echo Installing the tools needed to build the app...
py -3 -m pip install -r requirements.txt pyinstaller || goto :error
echo.
echo Building Chat Analyzer.exe. This takes about 20 minutes...
py -3 -m PyInstaller --noconfirm --clean --onefile --name "Chat Analyzer" ^
  --distpath "%USERPROFILE%\Downloads" --workpath "%TEMP%\chat_analyzer_build" --specpath "%TEMP%\chat_analyzer_build" ^
  --add-data "%~dp0whatsapp_analyzer.py;." ^
  --collect-all streamlit --copy-metadata streamlit ^
  --collect-data plotly --collect-data emoji ^
  exe_launcher.py || goto :error
echo.
echo Done. "Chat Analyzer.exe" is in your Downloads folder.
pause
exit /b 0

:error
echo.
echo The build failed. Is Python 3.10 or newer installed from python.org?
pause
