@echo off
setlocal

rem =============================================================
rem  boardgames - double-click launcher
rem
rem  Encoding: UTF-8 (no BOM), but the body is deliberately
rem  ASCII-only. cmd.exe decodes a .bat with the system ANSI
rem  codepage (GBK on a zh-CN Windows), so any non-ASCII byte
rem  here would become mojibake. Explanations live in README.md.
rem =============================================================

rem Always run from the directory this .bat lives in.
cd /d "%~dp0"

rem --- check uv -------------------------------------------------
where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo [uv not found] This project uses uv to manage Python and deps.
    echo                 Install it first: https://docs.astral.sh/uv/
    echo.
    pause
    exit /b 1
)

rem --- two critical settings - do not remove --------------------
rem If the project path contains non-ASCII characters (Chinese etc),
rem the editable install writes a .pth holding the UTF-8 path to
rem src/, but site.py on Windows reads .pth with the system ANSI
rem codec (GBK) -> mojibake path -> directory not found -> src/ is
rem skipped -> "ModuleNotFoundError: No module named 'boardgames'".
rem PYTHONUTF8=1 makes .pth be read as UTF-8 (PEP 540);
rem PYTHONPATH is a second safety net.
set "PYTHONUTF8=1"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

rem --- run (-m instead of the console script: one less launcher) -
uv run python -m boardgames.app %*
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [failed] exit code %EXITCODE% - see the error output above.
    echo.
    pause
)

endlocal & exit /b %EXITCODE%
