@echo off
REM SurgiCase Monitoring Stack Startup Script for Windows

echo 🚀 Starting SurgiCase Monitoring Stack...

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker is not running. Please start Docker and try again.
    pause
    exit /b 1
)

REM Check if docker-compose is available
docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo ❌ docker-compose is not installed. Please install docker-compose and try again.
    pause
    exit /b 1
)

REM Navigate to monitoring directory
cd /d "%~dp0.."

REM Pull latest images
echo 📥 Pulling latest Docker images...
docker-compose pull

REM Start services
echo 🔧 Starting monitoring services...
docker-compose up -d

REM Wait for services to be ready
echo ⏳ Waiting for services to be ready...
timeout /t 10 /nobreak >nul

REM Check service status
echo 📊 Checking service status...
docker-compose ps

REM Test Prometheus
echo 🔍 Testing Prometheus...
curl -s http://localhost:9090/api/v1/status/config >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Prometheus might still be starting up...
) else (
    echo ✅ Prometheus is running at http://localhost:9090
)

REM Test Grafana
echo 🔍 Testing Grafana...
curl -s http://localhost:3000/api/health >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Grafana might still be starting up...
) else (
    echo ✅ Grafana is running at http://localhost:3000
    echo    Default credentials: admin/admin
)

echo.
echo 🎉 Monitoring stack started successfully!
echo.
echo 📋 Access URLs:
echo    Prometheus: http://localhost:9090
echo    Grafana:    http://localhost:3000 (admin/admin)
echo    SurgiCase:  http://localhost:8000
echo    Metrics:    http://localhost:8000/metrics
echo.
echo 📝 Next steps:
echo    1. Start your SurgiCase API: python main.py
echo    2. Open Grafana and add Prometheus as a data source
echo    3. Import the SurgiCase dashboard
echo.
echo 🛑 To stop monitoring: stop-monitoring.bat
pause 