@echo off
rem ============================================================================
rem  StockMaster - point d'entree double-clic.
rem  Tout le travail est fait par demarrage.ps1 (voir DEMARRAGE.md) ; ce fichier
rem  le lance en contournant la politique d'execution PowerShell pour cette seule
rem  execution, sans modifier la configuration de la machine.
rem
rem  Utilisation :
rem    demarrage.bat                     mode developpement
rem    demarrage.bat prod                mode production (waitress + Caddy)
rem    demarrage.bat dev -SansCelery     toute option de demarrage.ps1 est transmise
rem    demarrage.bat prod -Caddy C:\caddy\caddy.exe -Port 8001
rem ============================================================================
setlocal
chcp 65001 >nul

set "ARGS=%*"
if /I "%~1"=="dev"  set "ARGS=-Mode %*"
if /I "%~1"=="prod" set "ARGS=-Mode %*"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0demarrage.ps1" %ARGS%
set "CODE=%ERRORLEVEL%"

if not "%CODE%"=="0" (
    echo.
    echo Le demarrage a echoue (code %CODE%). Lisez le message ci-dessus.
    pause
)
endlocal & exit /b %CODE%
