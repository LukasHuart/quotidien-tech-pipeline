@echo off
chcp 65001 >nul
cd /d "%~dp0"
git add .
git commit -m "Meilleur regroupement des doublons"
git push
echo.
echo Si vous voyez une erreur ci-dessus, copiez-la et envoyez-la a Claude.
pause
