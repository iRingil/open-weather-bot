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

echo Pybabel found. Updating locales from the .pot file...

:: Define the list of languages to update.
set "all_locales=en ru uk"

:: Loop through each locale and run the 'update' command for it.
for %%L in (%all_locales%) do (
    echo Updating language: %%L

    "%PYBABEL_EXE%" update ^
        --input-file=./src/locales/messages.pot ^
        --output-dir=./src/locales ^
        --width=120 ^
        --init-missing ^
        --update-header-comment ^
        --locale=%%L

    :: Check if the 'update' command for this specific locale failed.
    if !errorlevel! neq 0 (
        echo.
        echo ERROR: Pybabel update failed for locale '%%L' with error code !errorlevel!.
        exit /b !errorlevel!
    )
)

echo.
echo Script finished successfully. All locales have been updated.

endlocal
