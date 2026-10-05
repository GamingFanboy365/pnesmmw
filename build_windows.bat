@echo off
cd /d "%~dp0"
rem Builds pnesmmw.exe (GUI) and pnesmmw-cli.exe (command line) with PyInstaller.
rem Needs Python 3.8+ from python.org (tkinter included).
python -m pip install --upgrade pyinstaller || goto :error
python -m PyInstaller --onefile --windowed --name pnesmmw pnesmmw.py || goto :error
python -m PyInstaller --onefile --console --name pnesmmw-cli pnesmmw.py || goto :error
copy /y pnesmmw.ini dist\ >nul
copy /y pnesmmw.mdb dist\ >nul
echo.
echo Done, the program is in the dist folder.
goto :eof
:error
echo Build failed.
exit /b 1
