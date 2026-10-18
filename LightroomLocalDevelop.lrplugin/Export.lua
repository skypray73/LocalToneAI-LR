local LrTasks=import 'LrTasks'
local LrDialogs=import 'LrDialogs'
local LrPathUtils=import 'LrPathUtils'
local export=dofile(LrPathUtils.child(_PLUGIN.path,'ExportCore.lua'))
LrTasks.startAsyncTask(function()
    local answer=LrDialogs.confirm('匯出期間，請暫停操作 Lightroom',
        '外掛將匯出選取照片的目前顯影效果。\n'..
        '開始後請勿切換照片、切換編目或調整滑桿。\n'..
        '看到「預覽匯出完成」視窗後，即可繼續操作。','開始匯出','取消')
    if answer~='ok' then return end
    local ok,err=LrTasks.pcall(function() export() end)
    if not ok then LrDialogs.message('Local export failed',tostring(err),'critical') end
end)
