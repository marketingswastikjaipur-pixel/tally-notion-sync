@echo off
title Prchi Voucher Notion Sync App (Port 5001)
echo =============================================================
echo   Launching Prchi Voucher Notion Sync App (Port 5001)
echo   Notion DB: f6d358b9623f4b32b0cf4969cb6ebf35
echo =============================================================
echo.
cd /d "%~dp0prchi_app"
python app.py
pause
