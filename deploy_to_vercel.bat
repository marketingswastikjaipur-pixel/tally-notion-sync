@echo off
title Deploy Tally Voucher App to Vercel
echo =============================================================
echo   Deploying Tally Voucher Notion Sync App to Vercel
echo =============================================================
echo.
echo Running Vercel deployment...
npx vercel --prod
echo.
echo Deployment finished! Press any key to exit.
pause
