@echo off
REM SurgiCase Monitoring Stack Stop Script for Windows

echo 🛑 Stopping SurgiCase Monitoring Stack...

REM Navigate to monitoring directory
cd /d "%~dp0.."

REM Stop services
echo 🔧 Stopping monitoring services...
docker-compose down

echo.
echo ✅ Monitoring stack stopped successfully!
echo.
echo 📝 To start again: start-monitoring.bat
pause 