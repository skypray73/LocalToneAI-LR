local LrTasks=import 'LrTasks'
local LrDialogs=import 'LrDialogs'
local LrPathUtils=import 'LrPathUtils'
local export=dofile(LrPathUtils.child(_PLUGIN.path,'ExportCore.lua'))
LrTasks.startAsyncTask(function()
    local ok,err=LrTasks.pcall(function() export() end)
    if not ok then LrDialogs.message('Local export failed',tostring(err),'critical') end
end)
