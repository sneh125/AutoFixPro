@echo off
title AutoFixPro Server (Port 8080)
echo ===================================================
echo   Starting AutoFixPro Server on Port 8080...
echo   URL: http://127.0.0.1:8080/
echo ===================================================
python manage.py runserver 8080
pause
