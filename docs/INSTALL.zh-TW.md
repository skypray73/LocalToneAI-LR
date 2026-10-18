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

<a id="ollama-environment"></a>

## C. 設定 Ollama 環境變數：模型放哪裡、怎麼關閉雲端

這一步是在 **Windows 設定「使用者環境變數」**，不是在 Lightroom 輸入，也不是建立一個叫 `OLLAMA_MODELS` 的資料夾。環境變數是告訴 Ollama 啟動時要使用的設定。

先在檔案總管建立 `C:\AI\Models\Ollama`。以下兩種方法 **擇一操作即可**，不用做兩次；**推薦使用方法二 PowerShell**，可一次設定三項變數，並立即套用到目前視窗。

### 方法一：Windows 中文介面（不熟悉指令可用這個）

1. 點 Windows **「開始」**，搜尋 **「環境變數」**。
2. 選 **「編輯您帳戶的環境變數」**。不同 Windows 版本名稱可能略有差異；如果開到「系統內容」，再按其中的 **「環境變數…」** 按鈕。
3. 在「環境變數」視窗上半部，找到 **「使用者變數」**（後面通常會顯示目前帳號）。本流程設定這一區，不需要修改下半部的「系統變數」。
4. 按上半部的 **「新增…」**，分別建立下表三項。同名變數已存在時，選取它再按 **「編輯…」**，更新數值即可。

| 「變數名稱」欄填入 | 「變數值」欄填入 | 用途 |
|---|---|---|
| `OLLAMA_MODELS` | `C:\AI\Models\Ollama` | 下載的 Qwen 模型存到這個資料夾 |
| `OLLAMA_NO_CLOUD` | `1` | 停用 Ollama 的雲端模型等雲端功能 |
| `OLLAMA_HOST` | `127.0.0.1:11434` | 讓 Ollama API 只綁定這台電腦的本機位址 |

5. 每新增一項按 **「確定」**；三項完成後，再按「環境變數」視窗的 **「確定」**。若還有外層設定視窗，也按「確定」關閉。
6. 關閉之前的 PowerShell 視窗，重新從「開始」開啟 PowerShell。**原本正在執行的 Ollama 也必須正常結束再啟動**，不會因為新增變數就自動更新。

欄位內容不要加引號，也不要把 `OLLAMA_MODELS=C:\AI\Models\Ollama` 整串填進「變數名稱」。應分成名稱與數值兩欄，例如：

```text
變數名稱：OLLAMA_MODELS
變數值  ：C:\AI\Models\Ollama
```

### 方法二：PowerShell 設定（推薦使用）

從「開始」開啟 PowerShell，貼上以下內容。前四行建立模型資料夾並永久儲存使用者設定；後三行讓目前視窗立即使用這些值：

```powershell
New-Item -ItemType Directory -Force 'C:\AI\Models\Ollama' | Out-Null
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', 'C:\AI\Models\Ollama', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '127.0.0.1:11434', 'User')
$env:OLLAMA_MODELS = 'C:\AI\Models\Ollama'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_HOST = '127.0.0.1:11434'
```

### 檢查設定，然後啟動 Ollama

在已套用設定的 PowerShell 執行：

```powershell
$env:OLLAMA_MODELS
$env:OLLAMA_NO_CLOUD
$env:OLLAMA_HOST
```

應依序顯示 `C:\AI\Models\Ollama`、`1`、`127.0.0.1:11434`。這只是檢查**目前 PowerShell 視窗**的設定，不能證明舊的 Ollama 服務已更新。

若 Ollama 原本已執行，桌面版可從通知區圖示正常結束；可攜版若是在 PowerShell 執行 `serve`，回到那個視窗按 **Ctrl+C** 結束該服務。確認沒有本地修圖工作正在使用它，再從帶有正確設定的 PowerShell 啟動：

```powershell
& 'C:\AI\Ollama\ollama.exe' serve
```

此視窗會持續執行服務，先保持開啟，再照下一節另外開視窗下載模型。若 11434 已被占用，代表仍有其他程式／服務占用；不要再開第二個服務，也不要假設它已讀到新設定。

**模型實際存放位置由正在執行的 Ollama 服務決定**，不只是下載指令視窗裡的變數。因此要先完成設定並重新啟動服務，再下載模型。改這個設定不會自動搬移先前下載在其他位置的模型。

依據：[Ollama 官方 Windows 模型位置說明](https://docs.ollama.com/windows)與 [Ollama FAQ：Windows 環境變數及停用雲端](https://docs.ollama.com/faq)。

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

<a id="check-xmp"></a>

### 檢查「自動將變更寫入附屬檔案 (XMP/ACR)」：完整中文步驟

這是 **Lightroom Classic 目前編目的設定**。在 Windows 中文介面，從程式最上方的選單列操作：

1. 開啟 Lightroom Classic，先開啟你準備修圖的編目。在「圖庫」或「編輯相片」模組都可以檢查。
2. 點最上方的 **「編輯(E)」**。
3. 在下拉選單中點 **「編目設定…」**，開啟標題為「編目設定」的視窗。
4. 點視窗上方的 **「中繼資料」** 分頁。它和「一般」「預視」「備份」等分頁並列，名稱依版本可能略有差異。
5. 在上方 **「編輯」** 區塊，找到 **「自動將變更寫入附屬檔案 (XMP/ACR)」**。若左邊方框有勾號，點一下取消；如果原本已經空白，就保持空白。
6. 確認方框內 **沒有勾號**，按視窗右下方 **「確定」** 儲存，不要按「取消」。需要時再打開同一頁，確認仍未勾選。

```text
Lightroom Classic 頂端選單
編輯(E)
└─ 編目設定…
   └─ 中繼資料
      └─ 編輯
         ☐ 自動將變更寫入附屬檔案 (XMP/ACR)

☐ 空白、沒有勾號＝關閉，符合本專案只改編目的使用方式。
☑ 有勾號＝開啟，請取消勾選後按「確定」。
```

較舊版本可能只顯示「自動將變更寫入 XMP」；Adobe 中文說明也使用「自動將更改寫入至 XMP 中」。它們指的是相同的自動寫入設定。英文名稱是 **Automatically Write Changes Into XMP**。

#### 關閉後，修圖結果存在哪裡？

仍會保存在 **Lightroom 編目**，曝光、陰影、亮部等滑桿調整不會因此消失，正常關閉再開 Lightroom 仍會讀取編目中的設定。這個選項控制的是是否另外自動寫入照片中繼資料／附屬檔案，不是是否保存編目。

| 狀態 | Lightroom 的行為 | 本專案應用 |
|---|---|---|
| 未勾選 | 顯影與中繼資料變更自動保存在編目；不因這個選項自動寫到來源檔案或其附屬檔案 | **採用此狀態** |
| 已勾選 | 除編目外，也自動將變更寫入 XMP／ACR 附屬檔案，或支援格式內的中繼資料 | 不符合使用者要求來源檔案與原資料夾保持原樣的方式 |

一般相機專屬 RAW（例如 NEF）的 XMP 通常放在來源照片旁邊；DNG、JPEG 等格式的中繼資料可能寫入檔案本身。這不等於把顯影效果直接烘焙成原始像素，但仍可能新增附屬檔案或修改檔案中繼資料。因此不能把「非破壞性修圖」解釋成來源檔案一定完全沒被寫入。

#### 檢查完還要知道的事

- 這是目前編目的設定；換另一份編目時，請在那份編目裡重新確認。
- 關閉它不會刪除已存在的 XMP／ACR，也不會回復先前已寫入的中繼資料；不需要為了用外掛而刪除既有附屬檔案。
- 關閉自動寫入後，手動執行 **「將中繼資料儲存至檔案」** 仍可能寫回來源或附屬檔案；若要維持來源不變，就不要執行這項動作。
- 外掛不能可靠替你讀取或關閉此選項，所以開始修圖時會請你確認。這份說明也不代表已替你更改 Lightroom 的設定。
- 編目、快取和獨立的 `C:\AI\LightroomJobs` 工作資料仍會寫入硬碟；請備份編目，因為它保存你的修圖設定。

選單路徑、關閉後只自動儲存到編目，以及手動寫入的差異，可對照 [Adobe 官方中文說明：中繼資料基本知識與動作](https://helpx.adobe.com/tw/lightroom-classic/desktop/organize-photos-in-lightroom-classic/metadata-basics-actions.html)。不同格式的寫入方式見 [Adobe 官方說明](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/metadata-basics-actions.html)。

設定好後，從 **圖庫 → 增效模組額外資訊** 選「本地分析並套用選取照片（全部）」或「本地分析並套用選取照片（僅未修改）」開始，見 [日常操作](USAGE.zh-TW.md)。若找不到選單，重新啟動 Lightroom 並確認外掛已載入。

## 更新已有安裝

關閉 Lightroom → 下載新專案 → 重跑 `Setup-LocalAI.ps1` → 重新開 Lightroom。原本模型與工作資料仍在各自資料夾，不需重拉 Qwen。執行目錄保留 `LightroomLocalDevelop` 名稱，避免現有 Lightroom 外掛路徑失效。

此安裝流程針對 Windows x64、Python 3.14。macOS、雲端版 Lightroom 與其他 Python 版本未宣稱相容。
