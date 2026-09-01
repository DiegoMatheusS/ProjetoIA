@echo off
setlocal
if "%~1"=="" (
  echo Uso: capturar_magalu_local.bat "URL_DO_PRODUTO"
  exit /b 1
)
python -m src.local_browser_capture "%~1" --output magalu_capture.json
if errorlevel 1 (
  echo.
  echo A captura terminou com aviso. Confira a mensagem acima.
  exit /b %errorlevel%
)
echo.
echo Arquivo criado: magalu_capture.json
endlocal
