@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON=py -3"
) else (
  where python >nul 2>nul
  if not %errorlevel%==0 (
    echo [BLOCKED] 找不到 Python 3.11 或更新版本。
    echo 請先安裝 Python，或把 python.exe 加入 PATH。
    pause
    exit /b 1
  )
  set "PYTHON=python"
)

echo [INFO] 啟動 Voice Lab 本機介面。模型不會由此啟動檔自動下載。
%PYTHON% -m voice_lab serve
if not %errorlevel%==0 (
  echo [FAILED] 啟動失敗，請查看上方訊息或執行：python -m voice_lab doctor
  pause
)
