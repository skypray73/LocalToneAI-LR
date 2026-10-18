local LrTasks=import 'LrTasks'
local LrDialogs=import 'LrDialogs'
local LrPathUtils=import 'LrPathUtils'
local apply=dofile(LrPathUtils.child(_PLUGIN.path,'ApplyCore.lua'))
LrTasks.startAsyncTask(function()
    local answer=LrDialogs.confirm('套用期間，請暫停操作 Lightroom',
        '選擇 plan.tsv 後，外掛會更新照片的顯影滑桿。\n'..
        '請勿切換照片、切換編目、調整滑桿或啟動其他修圖工作。\n'..
        '看到套用完成視窗後，即可繼續操作。\n\n'..
        '請先確認「編目設定 → 中繼資料」中的\n'..
        '「自動將變更寫入附屬檔案 (XMP/ACR)」未勾選。',
        '已確認，選擇修圖計畫','取消')
    if answer~='ok' then return end
    local state={applied=0}
    local ok,err=LrTasks.pcall(function() apply(nil,nil,state) end)
    if not ok then LrDialogs.message('Local apply stopped',tostring(err)..'\nCompleted calls: '..state.applied..
        '\n未建立快照；需要時查看步驟記錄。','critical') end
end)
