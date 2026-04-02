@echo off
echo ====================================
echo  [POS] Print Agent - Build Script
echo ====================================
echo.

REM ── Output path for the distributable .exe ─────────────────────────
set "DEFAULT_DIST=%~dp0dist"
set /p "DIST_PATH=Ruta de salida del .exe (Enter = %DEFAULT_DIST%): "
if "%DIST_PATH%"=="" set "DIST_PATH=%DEFAULT_DIST%"

echo.
echo  Output: %DIST_PATH%
echo.

REM ── Install PyInstaller if missing ─────────────────────────────────
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    python -m pip install pyinstaller
)

echo.
echo Compilando [POS] Print Agent...
echo.

python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name=POSPrintAgent ^
    --icon=static\logo.ico ^
    --distpath="%DIST_PATH%" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --hidden-import=win32print ^
    --hidden-import=win32ui ^
    --hidden-import=win32con ^
    --hidden-import=win32gui ^
    --hidden-import=pystray ^
    --hidden-import=pystray._win32 ^
    --hidden-import=webview ^
    --hidden-import=webview.platforms.edgechromium ^
    --exclude-module=numpy ^
    --exclude-module=numpy.typing ^
    --exclude-module=numpy.core ^
    --exclude-module=numpy._core ^
    app.py

echo.
if errorlevel 1 (
    echo [ERROR] Build fallido.
) else (
    echo [OK] Build exitoso^^!
    echo      Distribuible: %DIST_PATH%\POSPrintAgent.exe
    echo.
    echo      Enviale ese .exe a tus trabajadores.
    echo      Al ejecutarlo, se instala solo en AppData y
    echo      pregunta si quieren acceso directo en el Escritorio.
)
echo.
pause
