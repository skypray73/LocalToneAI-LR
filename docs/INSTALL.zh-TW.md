# 從零安裝：先準備 AI，再加入 Lightroom

要安裝的元件與完整資料夾配置先看 [首頁第 1、2 節](../README.md)。安裝下載需要網路，照片推論在本機執行。

## A. Python 3.14（64 位元）

1. 到 [Python 官方 Windows 下載頁](https://www.python.org/downloads/windows/) 下載 Python 3.14 的 64 位元安裝程式。
2. 安裝時加入 PATH。安裝完成後重新開啟 PowerShell。
3. 執行：

```powershell
python --version
python -c "import sys; print(64 if sys.maxsize > 2**32 else 32)"
```

預期顯示 `Python 3.14.x` 與 `64`。若 `python` 開啟 Microsoft Store 或指到其他版本，請使用實際 `python.exe` 完整路徑，稍後傳給安裝腳本的 `-PythonExe`。

## B. Ollama 執行程式

1. 到 [Ollama 官方 Releases](https://github.com/ollama/ollama/releases/latest)。
2. 在 Assets 下載 **ollama-windows-amd64.zip**。
3. 建立 `C:\AI\Ollama`，將 ZIP **全部內容**解壓到這裡，包括 GPU 程式庫。
4. 確認 `C:\AI\Ollama\ollama.exe` 存在，沒有多一層 ZIP 資料夾。

本專案採官方可攜版，因為自動啟動會尋找這個固定路徑。只裝桌面版、放在其他地方時，不能假設外掛找得到。已有 Ollama 服務時勿同時開第二個服務；先確認它的模型目錄與本地設定。

依據：[Ollama 官方 Windows 說明](https://docs.ollama.com/windows)。NVIDIA 顯示卡請先安裝可支援你顯示卡的官方驅動程式。

## C. 指定模型位置並關閉雲端

在 PowerShell 執行：

```powershell
New-Item -ItemType Directory -Force 'C:\AI\Models\Ollama' | Out-Null
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', 'C:\AI\Models\Ollama', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '127.0.0.1:11434', 'User')
$env:OLLAMA_MODELS = 'C:\AI\Models\Ollama'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_HOST = '127.0.0.1:11434'
& 'C:\AI\Ollama\ollama.exe' serve
```

最後一行會持續執行服務，先保持視窗開啟。若 11434 已被占用，通常是既有 Ollama 正在執行；不要啟動第二個。**既有服務不會自動讀到剛改的環境變數**，需先正常結束原服務，再從帶有上述設定的 PowerShell 啟動。

User 環境變數供未來新程序繼承；`$env:` 是讓目前視窗立即生效。關閉雲端後仍需重啟既有服務。依據：[Ollama FAQ](https://docs.ollama.com/faq)。

## D. 下載看照片的 AI 模型

另開 PowerShell 視窗，執行：

```powershell
$env:OLLAMA_MODELS = 'C:\AI\Models\Ollama'
& 'C:\AI\Ollama\ollama.exe' pull qwen3-vl:8b-instruct
& 'C:\AI\Ollama\ollama.exe' list
```

等待下載完成，確認清單包含 **qwen3-vl:8b-instruct**。約 6.1GB 是這個模型的下載量，另外還要預留 Ollama、Python、套件與預覽工作資料的空間。

不要改成 `qwen3-vl:8b`、Thinking 或 cloud 版本；程式預設與輸出格式是針對明確的 Instruct 標籤。資料由 Ollama 存到 `C:\AI\Models\Ollama`，不要手動移動其中的 blobs。

依據：[Ollama 模型頁](https://ollama.com/library/qwen3-vl:8b-instruct)。首次下載完成後，日常不用重複下載。

## E. 安裝專案、Python 依賴與人臉偵測

1. GitHub 專案頁按 **Code → Download ZIP**，完整解壓到任意暫存位置。
2. 開啟解壓後、有 `Setup-LocalAI.ps1` 的資料夾，在 PowerShell 切換到該目錄。
3. 執行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-LocalAI.ps1
```

`Bypass` 僅對這次 PowerShell 程序，不會永久修改系統執行原則。可先閱讀腳本，或用 `-PlanOnly` 列出動作。此腳本只安裝本專案，不下載或啟動 Ollama、不下載 Qwen、不操作照片或編目。

若 Python 不在 PATH，改成：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-LocalAI.ps1 -PythonExe '你的 Python 3.14 完整路徑\python.exe'
```

腳本會複製外掛、程式、隨附 YuNet 模型和文件到 `C:\AI\LightroomLocalDevelop`，建立 `.venv`，從 PyPI 安裝 Pillow、OpenCV 與 NumPy。不會把 Qwen 或大型 Python 二進位套件上傳到 GitHub。

成功後確認：

```powershell
& 'C:\AI\LightroomLocalDevelop\.venv\Scripts\python.exe' -c "import PIL,cv2,numpy; print('依賴可用')"
Test-Path 'C:\AI\LightroomLocalDevelop\models\face_detection_yunet_2023mar.onnx'
Invoke-RestMethod 'http://127.0.0.1:11434/api/version'
```

三項分別應顯示「依賴可用」、`True` 和 Ollama 版本。既有舊版的 `python_deps` 不必為更新而刪除；新版啟動器優先使用 `.venv`，避免混用不同 Python 的二進位依賴。

## F. Lightroom 只需要設定兩處

### 加入外掛

**檔案 → 增效模組管理員 → 新增**，選取：

```text
C:\AI\LightroomLocalDevelop\LightroomLocalDevelop.lrplugin
```

選整個 `.lrplugin` 資料夾，不是其中的 Lua 檔，也不是下載的 ZIP。確認外掛名稱 **本地 AI 顯影** 已啟用。英文選單是 **File → Plug-in Manager → Add**；中文版本可能用「增效模組」或「外掛程式」等字樣。

### 關閉自動寫入來源中繼資料

Windows：**編輯 → 編目設定 → 中繼資料**，取消勾選：

> 自動將變更寫入附屬檔案 (XMP/ACR)

這個選項必須關閉，才能符合只改編目、不寫回來源檔案的使用方式。外掛不能可靠替你讀取或切換這個選項。

設定好後，從 **圖庫 → 增效模組額外資訊 → 本地分析並套用選取照片** 開始，見 [日常操作](USAGE.zh-TW.md)。若找不到選單，重新啟動 Lightroom 並確認外掛已載入。

## 更新已有安裝

關閉 Lightroom → 下載新專案 → 重跑 `Setup-LocalAI.ps1` → 重新開 Lightroom。原本模型與工作資料仍在各自資料夾，不需重拉 Qwen。執行目錄保留 `LightroomLocalDevelop` 名稱，避免現有 Lightroom 外掛路徑失效。

此安裝流程針對 Windows x64、Python 3.14。macOS、雲端版 Lightroom 與其他 Python 版本未宣稱相容。
