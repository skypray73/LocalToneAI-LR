# SKILL 使用方法（選用）

日常修圖入口是 Lightroom 外掛。**SKILL 不是本地模型、不會自行常駐，也不是 Lightroom 必裝項目。** 它是一套給相容 AI 助理讀取的工作流程，協助安裝、修改規則、理解紀錄與排錯；執行推論的仍是本機 Ollama／Qwen。

## 檔案在哪裡？

```text
skills\lightroom-auto-develop\
├─ SKILL.md                  工作流程與必要限制
└─ references\              安裝、操作和規則說明
```

安裝到支援本地 Agent Skills 的工具時，將**整個 `lightroom-auto-develop` 資料夾**放到該工具的技能目錄，不是只複製 SKILL.md。外掛與分析器仍依 [安裝文件](INSTALL.zh-TW.md) 放到 `C:\AI\LightroomLocalDevelop`，兩者用途不同。

例如支援 `.agents/skills` 的工具，可放在專案內 `.agents/skills/lightroom-auto-develop` 或使用者層級 `%USERPROFILE%\.agents\skills\lightroom-auto-develop`。不同工具的載入與呼叫方式不同，請依其說明；Codex 的本地技能位置與顯式呼叫方式見 [官方技能文件](https://learn.chatgpt.com/docs/build-skills)。既有安裝在舊目錄時避免同名重複安裝。

## 可以怎麼叫它幫忙？

在支援 `$技能名稱` 的工具中，例如：

```text
$lightroom-auto-develop
依照 LumaPilot 的文件幫我檢查本地環境：Ollama、Qwen 模型、Python 和外掛路徑。
不要修改照片或編目。
```

```text
使用 lightroom-auto-develop，幫我解釋這次 report.json 與 tone-verification.json。
先只讀取文字紀錄，說明哪些是實際亮暗微調、固定規則、未確認和被保護擋下的建議。
```

```text
使用 lightroom-auto-develop，將風景清晰度與去朦朧目標調整成我指定的數值，
同步更新規則說明並做必要驗證，保持原始照片不變。
```

不支援技能載入的工具，也能直接閱讀這些文件；但那不代表它自動具備操作 Lightroom 的權限或能力。

## 本地照片原則

這個 SKILL 要求照片分析留在本機；AI 助理預設只讀設定、程式和文字紀錄，不將照片、臉部拼圖或 RAW 上傳雲端看圖。紀錄可能含私人路徑，分享給其他服務前應先去識別化。使用遠端聊天助理討論規則，與本機執行照片推論是兩件事。

SKILL 不會繞過 Lightroom SDK、直接改 `.lrcat`、儲存來源中繼資料或強迫套用待確認計畫。實際批次修改應從 Lightroom 的選取照片入口執行。
