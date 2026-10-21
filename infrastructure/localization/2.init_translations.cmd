@echo off
setlocal enabledelayedexpansion

:: Change directory to the project root.
cd /d "%~dp0..\.."
echo Current working directory is: %cd%

:: Define the path to pybabel relative to the project root.
set "PYBABEL_EXE=.\.venv\Scripts\pybabel.exe"

:: Check if the pybabel executable exists.
if not exist "%PYBABEL_EXE%" (
    echo ERROR: pybabel.exe not found in %cd%\.venv\Scripts\
    exit /b 1
)

echo Pybabel found. Initializing locales...

:: Define the list of languages to initialize.
set "all_locales=en ru uk"

:: Loop through each locale and run the 'init' command for it.
for %%L in (%all_locales%) do (
    echo Initializing language: %%L

    "%PYBABEL_EXE%" init ^
        --input-file="./src/locales/messages.pot" ^
        --output-dir="./src/locales" ^
        --width=120 ^
        --locale="%%L"

    :: Check if the 'init' command for this specific locale failed.
    if !errorlevel! neq 0 (
        echo.
        echo ERROR: Pybabel init failed for locale '%%L' with error code !errorlevel!.
        exit /b !errorlevel!
    )
)

echo.
echo Script finished successfully. New language directories should be created.

endlocal
