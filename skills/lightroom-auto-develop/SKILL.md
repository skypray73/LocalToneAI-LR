---
name: lightroom-auto-develop
description: 協助安裝、維護和排查 LocalToneAI 本地 AI Lightroom Classic 修圖外掛，解釋修圖計畫與批次紀錄，依需求修改人像、風景和夜景規則。
---

# LocalToneAI 本地 AI 輔助 Lightroom 修圖

日常入口是「圖庫 → 增效模組額外資訊 → 本地分析並套用選取照片」。技能提供安裝與維護流程，不是照片推論服務。先依使用者需求選讀 [安裝](references/INSTALL.zh-TW.md)、[操作與排錯](references/USAGE.zh-TW.md)、[規則](references/RULES.zh-TW.md)。

## 本地元件

Ollama 執行程式 `C:\AI\Ollama\ollama.exe`；模型 `qwen3-vl:8b-instruct` 存在 `C:\AI\Models\Ollama`。外掛、分析器、YuNet 與獨立 Python 環境在 `C:\AI\LightroomLocalDevelop`；批次資料在 `C:\AI\LightroomJobs`。對應程式碼在來源專案根目錄的 `scripts`、`LightroomLocalDevelop.lrplugin`，更新時先驗證來源再同步執行目錄。

照片、RAW、臉部拼圖的分析留在本機；預設只讀程式、設定及文字紀錄，不交給雲端模型看圖。推論 API 只連 `127.0.0.1:11434`，禁止 cloud 模型、HTTP 重新導向與系統代理。已有 Ollama 服務時確認其設定，不能宣稱新程序的環境變數已改變既有服務。

## 修圖流程與限制

逐張 LR 原生 Auto → 等待顯影數值穩定 → 重新正式轉存預覽 → 本地模型看目前圖與臉部拼圖 → 產生增量計畫 → 編目／ID／完整路徑與 baseline 檢查 → SDK 套回。每張保留 pipeline_stage：有觀察到變更為 after-lightroom-auto，穩定未變為 current-develop。不能直接改編目資料庫，不用舊快取縮圖，不把微調加在與預覽不同的 baseline。

1.12.2 每張自動色調只呼叫一次；穩定無變化約 3 秒列 unchanged_stable_current，可用目前顯影設定接續 AI，但不計入已確認 Auto 變更。控制未就緒或數值不穩定才列 unverified 並略過。已變動仍需連續穩定。慢載入可能超過確認窗；轉存及套回均需 baseline 檢查。不能因穩定在 0 就稱 Auto 成功；已等於 Auto 結果也可能無變化，不能一律說失敗。取消或後續錯誤時，已完成修改不自動回復。分別報告基礎數值確認、穩定未變、未確認、AI 微調、固定偏好和待確認張數。

目前偏好：人像 Sharpness=0，正值 LR Auto Vibrance ×0.7 四捨五入，其餘色彩保留；風景 Clarity2012=20、Dehaze=20 為絕對目標，保留銳利化與 LR Auto 色彩。兩者列 policy_settings，不能混成模型自主調整。夜景由模型另判，陰影增量 ±100，其他情境 ±70；曝光 ±0.5EV、亮部 ±70、白黑 ±25及高光保護不放寬。實際界限以程式為準，不固定拉滿。

臉頰／額頭只是由五官推算並以色度過濾的皮膚候選區域，不是精確皮膚分割。至少兩可靠區域偏暗才啟用量測補光；模型認為足夠但量測符合條件時，小幅補光依使用者偏好，標為 measured_skin_fill_preference，不偽稱 AI 也認同欠曝。仍是全圖滑桿，沒有局部遮色片。模型有時整批給 0，不應宣稱所有照片已最佳。

## 來源照片保護與驗證

1.12.0 起模型回覆不完整或暫時錯誤只重試一次，持續失敗逐張記錄並略過，其他成功計畫仍可套用。LRRESULT v4 分列失敗數，不把失敗混成無需微調或待確認。致命流程錯誤仍停止。舊版整批被單張失敗阻擋時，可用 scripts/resume_failed.py 保留舊決策、只重試失敗身分，另存新 plan.tsv；仍需原編目、原選取與 baseline 檢查後手動套用。不得宣稱產生計畫代表 Lightroom 已套用；已套用部分批次不能盲目重複。

不覆寫、移動或改名 RAW／DNG，不寫 sidecar、不儲存來源中繼資料、不更新 DNG。不建立快照或刪除既有快照。必須提醒 LR「編目設定 → 中繼資料 → 自動將變更寫入附屬檔案 (XMP/ACR)」保持未勾選；不能宣稱外掛能可靠讀取或關閉它。編目、快取與獨立工作區仍需寫硬碟。

文字紀錄含私人路徑與量測資料，公開分享前去識別化，不把批次資料或照片放進來源儲存庫。report.json 是計畫紀錄，lightroom_applied／visual_verified 不會由外掛回寫，不能憑它證明最終狀態。測試通過、SDK 呼叫返回、計畫已產生與實際 LR 視覺品質分開陳述。

修改程式後驗證相應邊界與回歸；既有測試以 `python -m unittest discover -s tests -p 'test_*.py'` 執行，不操作真實編目。首次新版用少量選取照片由使用者在 LR 確認，不盲目重跑整批。
