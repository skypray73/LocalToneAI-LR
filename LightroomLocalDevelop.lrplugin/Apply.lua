local LrTasks=import 'LrTasks'
local LrDialogs=import 'LrDialogs'
local LrPathUtils=import 'LrPathUtils'
local apply=dofile(LrPathUtils.child(_PLUGIN.path,'ApplyCore.lua'))
LrTasks.startAsyncTask(function()
    local state={applied=0}
    local ok,err=LrTasks.pcall(function() apply(nil,nil,state) end)
    if not ok then LrDialogs.message('Local apply stopped',tostring(err)..'\nCompleted calls: '..state.applied..
        '\n未建立快照；需要時查看步驟記錄。','critical') end
end)
