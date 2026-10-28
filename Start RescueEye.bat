@echo off
rem Starts RescueEye on this laptop: the API (which also starts MediaMTX for
rem drone streams), the public tunnel if one is set up, and the local website.
rem Each opens in its own window - keep them open while RescueEye is in use.
setlocal
set "ROOT=%~dp0"
set "CLOUDFLARED=%ROOT%..\tools\cloudflared.exe"

echo Starting RescueEye API...
start "RescueEye API - keep open" /D "%ROOT%api" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"

rem The permanent tunnel exists once "cloudflared tunnel create rescueeye" has been run.
if exist "%USERPROFILE%\.cloudflared\cert.pem" if exist "%CLOUDFLARED%" (
  echo Starting the public tunnel...
  start "RescueEye tunnel - keep open" cmd /k ""%CLOUDFLARED%" tunnel run --url http://localhost:8000 rescueeye"
) else (
  echo No permanent tunnel set up yet - phones must be on the same Wi-Fi as this laptop.
)

rem Local website, for when the Vercel site isn't used (e.g. no internet at the venue).
echo Starting the local website...
start "RescueEye website - keep open" /D "%ROOT%" cmd /k "npm run dev"

echo.
echo Wi-Fi address for the phone app (Server: ... Change):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4" ^| findstr "192.168."') do for /f "tokens=*" %%b in ("%%a") do echo    http://%%b:8000
echo.
echo Website: http://localhost:5173  (wait about 20 seconds for the API to load its AI models)
echo.
pause
