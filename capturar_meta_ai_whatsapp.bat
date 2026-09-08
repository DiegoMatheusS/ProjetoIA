@echo off
setlocal
cd /d "%~dp0"
python -m src.meta_ai_whatsapp_capture --output meta_ai_whatsapp_capture.json
if errorlevel 1 (
  echo.
  echo Falha ao capturar a resposta. Confira se o chat do Meta AI estava aberto e com a resposta visivel.
  pause
  exit /b 1
)
echo.
echo Captura concluida: meta_ai_whatsapp_capture.json
pause
