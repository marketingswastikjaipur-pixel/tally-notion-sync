@echo off
title Push Project to GitHub
echo =============================================================
echo               Push Project to GitHub Repository
echo =============================================================
echo.
echo Please copy your GitHub repository URL (e.g. https://github.com/username/repo-name.git)
set /p REPO_URL="Enter your GitHub Repository URL: "

if "%REPO_URL%"=="" (
    echo Error: No URL entered!
    pause
    exit /b
)

echo.
echo [1/3] Adding remote origin...
git remote remove origin 2>nul
git remote add origin %REPO_URL%

echo [2/3] Setting branch to main...
git branch -M main

echo [3/3] Pushing to GitHub...
git push -u origin main

echo.
if %ERRORLEVEL% equ 0 (
    echo =============================================================
    echo [SUCCESS] Project successfully pushed to GitHub!
    echo Now open https://vercel.com and import this repository to deploy.
    echo =============================================================
) else (
    echo [ERROR] Push failed. Please verify your repository URL and login credentials.
)

pause
