# Voice Lab 本機聲音研究工具

第一版是 Windows 本機使用的瀏覽器介面，先完成「環境檢查 → 登記本機音檔 → FFmpeg 探測／裁切／輕度清理 → 輸出 WAV → 保存 Log」。目前**不下載、不安裝、不假裝執行大型 TTS／VC 模型**。

## 啟動

在本資料夾雙擊：

```text
start.cmd
```

或在 PowerShell 執行：

```powershell
python -m voice_lab doctor
python -m voice_lab serve
```

啟動後使用瀏覽器開啟 `http://127.0.0.1:8000/`。資料預設寫入 `data/`；此資料夾已加入 `.gitignore`，不會被提交到 GitHub。若要放到其他磁碟：

```powershell
$env:VOICE_LAB_DATA_ROOT = 'D:\VoiceLabData'
python -m voice_lab serve
```

## 第一版可以做什麼

- 建立本機研究專案。
- 登記本機音訊／影片檔案，不會上傳到網路。
- 使用 `ffprobe` 查看媒體資訊。
- 使用 `ffmpeg` 裁切為單聲道、48 kHz、16-bit WAV。
- 選擇「原音」或「輕度清理」版本。
- 每個動作保存 `run-id`、進度、標準輸出、錯誤輸出與診斷摘要。
- 執行模型大小檢查；超過 4 GiB 的模型禁止下載，第一版也不會自動下載模型。

第一版尚未完成 TTS、VC、ASR、訓練及 YouTube 下載。這些入口先保持清楚的「待接入」狀態，避免沒有真實模型測試卻顯示成功。

## 目錄

```text
voice_lab/       Python 本機服務、資料處理與模型大小政策
ui/              本機網頁介面
tests/           不需要模型的單元測試
docs/            部署與第三方整合邊界
data/            執行後產生，已忽略，不進 Git
```

## 驗證

```powershell
python -m unittest discover -s tests -v
python -m compileall -q voice_lab tests
python -m voice_lab model-check 4294967297
```

最後一個命令應以退出碼 `2` 結束，並顯示模型超過 4 GiB、禁止下載。這是政策測試，不會下載檔案。

## 安全與素材邊界

請只使用自己錄製或已取得合法使用權的聲音素材。模型、音檔、Cookie、Token、執行輸出不應提交到 GitHub。若要使用第三方專案，先查看其授權、依賴與模型授權，再決定是否接入。
