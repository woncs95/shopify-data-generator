@echo off
cd /d "%~dp0infra\searxng"
set "DOCKER=docker"
where docker >nul 2>nul
if errorlevel 1 set "DOCKER=C:\Program Files\Docker\Docker\resources\bin\docker.exe"
"%DOCKER%" compose up -d
