@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod 'http://localhost:8888/search?q=VT%%20Cosmetics%%20Reedle%%20Shot%%20300&format=json' | Select-Object -ExpandProperty results | Select-Object -First 3 title,url"
