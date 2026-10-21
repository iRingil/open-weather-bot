@echo off
setlocal

:: Change directory to the project root.
:: %~dp0 is the script's directory, '../..' moves two levels up to the project root.
cd /d "%~dp0..\.."
echo Current working directory is: %cd%

:: Define the path to pybabel relative to the project root.
set "PYBABEL_EXE=.\.venv\Scripts\pybabel.exe"

:: Check if the pybabel executable exists.
if not exist "%PYBABEL_EXE%" (
    echo ERROR: pybabel.exe not found in %cd%\.venv\Scripts\
    exit /b 1
)

echo Pybabel found. Running compile...

:: Call pybabel directly to compile the translations.
"%PYBABEL_EXE%" compile ^
--directory=./src/locales ^
--statistics

:: Check if the previous command executed successfully.
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Pybabel command failed with error code %errorlevel%.
    echo Compilation might be incomplete.
    exit /b %errorlevel%
)

echo.
echo Script finished successfully. Your .po files have been compiled into .mo files.

endlocal
