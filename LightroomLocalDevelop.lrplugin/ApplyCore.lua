local LrApplication=import 'LrApplication'
local LrDialogs=import 'LrDialogs'
local LrTasks=import 'LrTasks'
local LrPathUtils=import 'LrPathUtils'
local M=dofile(LrPathUtils.child(_PLUGIN.path,'Common.lua'))

return function(path,options,state)
    options=options or {}
    state=state or {applied=0}

        if not path then
            local chosen=LrDialogs.runOpenPanel{title='Choose Local plan.tsv',canChooseFiles=true,
                canChooseDirectories=false,allowsMultipleSelection=false,fileTypes={'tsv'}}
            if not chosen then return end
            path=chosen[1]
        end
        local expected,items,order=M.readPlan(path)
        local catalog=LrApplication.activeCatalog()
        if catalog:getPath()~=expected then error('Catalog mismatch. Re-export from this catalog.') end
        local selected={}
        for _,p in ipairs((options.photos or catalog:getTargetPhotos())) do selected[tostring(p.localIdentifier)]=p end
        local function check()
            for _,id in ipairs(order) do
                local item,p=items[id],selected[id]
                if not p or p:getRawMetadata('path')~=item.path then error('Photo not selected or path mismatch: '..id) end
                local current=M.settings(p)
                for k,v in pairs(item.baseline) do
                    if not M.same(current[k],v) then error('Baseline changed: '..id..'/'..k..'. Re-export and analyse again.') end
                end
                local s=item.settings
                local raw=p:getRawMetadata('fileFormat')=='RAW' or p:getRawMetadata('fileFormat')=='DNG'
                if (raw and (s.RelativeTemperature or s.RelativeTint)) or
                    (not raw and (s.Temperature or s.Tint)) then error('White balance units mismatch: '..id) end
                if (s.Temperature or s.Tint or s.RelativeTemperature or s.RelativeTint) and
                    s.WhiteBalance~='Custom' then error('Missing Custom WB: '..id) end
            end
        end
        check()
        local hasAuto=false
        for _,id in ipairs(order) do if items[id].autoTone then hasAuto=true end end
        if hasAuto then
            for _,id in ipairs(order) do
                if not items[id].autoTone then error('不能混合自動與手動色調計畫，未開始套用。') end
            end
            local runAuto=dofile(LrPathUtils.child(_PLUGIN.path,'AutoToneCore.lua'))
            local savedSelection=options.photos or catalog:getTargetPhotos()
            local savedTarget=catalog:getTargetPhoto()
            local success,message=LrTasks.pcall(function()
                for _,id in ipairs(order) do
                    local photo,item=selected[id],items[id]
                    if item.autoTone then runAuto(catalog,photo,item,state)
                    else error('不能混合自動與手動色調計畫') end
                end
            end)
            catalog:setSelectedPhotos(savedTarget or savedSelection[1],savedSelection)
            if not success then error(message) end
            if not options.silent then
                LrDialogs.message('自動亮度與對比校正完成',state.applied..' 張已處理。\n可以繼續操作 Lightroom，請在編輯相片查看滑桿。','info')
            end
            return state.applied
        end
        catalog:withWriteAccessDo('本地 AI 顯影',function()
            check() -- Validate entire batch again under the write lock, before first mutation.
            for _,id in ipairs(order) do
                local photo=selected[id]
                photo:applyDevelopSettings(items[id].settings,'本地 AI 顯影')
                state.applied=state.applied+1
            end
        end,{timeout=30})
        if state.applied~=#order then error('Write access incomplete; expected '..#order..', processed '..state.applied) end
        if not options.silent then
            LrDialogs.message('修圖計畫套用完成',state.applied..' 張已套用。\n可以繼續操作 Lightroom，請到「編輯相片」查看效果。','info')
        end
        return state.applied

end
