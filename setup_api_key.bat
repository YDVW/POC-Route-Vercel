@echo off
echo Setting up OpenRouteService API Key
echo =====================================
echo.
echo Please enter your OpenRouteService API key when prompted.
echo You can get a free API key at: https://openrouteservice.org/dev/#/signup
echo.
echo The free plan includes:
echo - 2000 requests per day
echo - 40 requests per minute
echo - No credit card required
echo.

set /p API_KEY="Enter your API key: "

if "%API_KEY%"=="" (
    echo No API key provided. Exiting...
    pause
    exit /b 1
)

echo.
echo Setting environment variable...
setx OPENROUTESERVICE_API_KEY "%API_KEY%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ API key set successfully!
    echo.
    echo The environment variable OPENROUTESERVICE_API_KEY has been set to: %API_KEY%
    echo.
    echo IMPORTANT:
    echo - You may need to restart your command prompt/PowerShell for the change to take effect
    echo - Or you can set it temporarily for this session with:
    echo   set OPENROUTESERVICE_API_KEY=%API_KEY%
    echo.
    echo You can now run your Flask app and it will use road routing!
) else (
    echo ❌ Failed to set environment variable.
    echo You can set it manually with:
    echo set OPENROUTESERVICE_API_KEY=%API_KEY%
)

echo.
pause 