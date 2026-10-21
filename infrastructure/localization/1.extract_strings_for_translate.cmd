@echo off
setlocal

:: Change directory to the project root.
cd /d "%~dp0..\.."
echo Current working directory is: %cd%

:: Defining the path to pybabel
set "PYBABEL_EXE=.\.venv\Scripts\pybabel.exe"

:: File existence check
if not exist "%PYBABEL_EXE%" (
    echo ERROR: pybabel.exe not found in %cd%\.venv\Scripts\
    exit /b 1
)

echo Pybabel found. Running extract...

:: Call pybabel
"%PYBABEL_EXE%" extract ^
-F ./infrastructure/localization/babel.cfg ^
--input-dirs=./src/ ^
--output-file=./src/locales/messages.pot ^
--width=120 ^
--sort-by-file ^
--msgid-bugs-address=i.ringil@proton.me ^
--copyright-holder=Ringil ^
--project=Open-Weather-Bot ^
--version=2.0.0

:: Verifying whether the previous command was successfully executed
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Pybabel command failed with error code %errorlevel%.
    echo The file messages.pot was NOT created or updated.
    exit /b %errorlevel%
)

echo.
echo Script finished successfully. The file messages.pot should now be in src/locales/

endlocal
