@echo off
echo Starting Route Optimizer with OpenRouteService API key...
echo.

REM Set the API key for this session
set OPENROUTESERVICE_API_KEY=your_api_key_here

REM Verify the API key is set
echo API Key: %OPENROUTESERVICE_API_KEY:~0,8%...
echo.

REM Start the Flask app
echo Starting Flask app...
python app.py

pause 