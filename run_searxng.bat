@echo off
cd /d "%~dp0infra\searxng"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\create_local_settings.ps1"
set "DOCKER=docker"
where docker >nul 2>nul
if errorlevel 1 set "DOCKER=C:\Program Files\Docker\Docker\resources\bin\docker.exe"
"%DOCKER%" compose up -d
