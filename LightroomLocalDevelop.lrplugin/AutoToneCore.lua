local LrApplicationView=import 'LrApplicationView'
local LrDevelopController=import 'LrDevelopController'
local LrTasks=import 'LrTasks'
local LrPathUtils=import 'LrPathUtils'
local M=dofile(LrPathUtils.child(_PLUGIN.path,'Common.lua'))
local tone={Exposure2012=true,Contrast2012=true,Highlights2012=true,
    Shadows2012=true,Whites2012=true,Blacks2012=true,Vibrance=true,Saturation=true}

return function(catalog,photo,item,state)
    if type(LrDevelopController.setAutoTone)~='function' then
        error('此 Lightroom SDK 不支援自動色調；未開始此張自動校正。')
    end
    local before=M.settings(photo)
    for key,value in pairs(item.baseline) do
        if not M.same(before[key],value) then error('自動校正前設定已變更：'..key) end
    end
    catalog:setSelectedPhotos(photo,{photo})
    local function isTarget()
        local target=catalog:getTargetPhoto()
        return target and target.localIdentifier==photo.localIdentifier
    end
    LrApplicationView.switchToModule('develop')
    local available,readySamples=false,0
    local lastReadings={}
    for _=1,80 do
        local matches=false
        -- Develop controls use Exposure; the settings table uses Exposure2012.
        -- Some localized SDK versions also accept the latter. Control values may be rounded.
        for _,name in ipairs({'Exposure','Exposure2012'}) do
            local ok,value=LrTasks.pcall(function() return LrDevelopController.getValue(name) end)
            if ok and type(value)=='number' then
                lastReadings[name]=value
                if type(before.Exposure2012)=='number' and math.abs(value-before.Exposure2012)<=0.011 then matches=true end
            end
        end
        if matches and isTarget() then
            readySamples=readySamples+1
        else readySamples=0 end
        -- Catalog selection can change before Develop has loaded the selected image.
        if readySamples>=2 then available=true;break end
        LrTasks.sleep(0.25)
    end
    if not available then
        state.unverified=(state.unverified or 0)+1
        state.toneResults=state.toneResults or {}
        state.toneResults[#state.toneResults+1]={photo_id=tostring(photo.localIdentifier),
            status='develop_control_unconfirmed',attempts=0,before=before,after=M.settings(photo),
            controller_readings=lastReadings,reason='編輯相片控制未確認，未呼叫這張自動校正；繼續其他照片。'}
        return false
    end
    for key,value in pairs(item.baseline) do
        if not M.same(M.settings(photo)[key],value) then error('自動校正前設定已變更') end
    end
    local after,verified,attempts=M.settings(photo),false,0
    for attempt=1,1 do
        attempts=attempt
        state.toneStarted=(state.toneStarted or 0)+1
        LrDevelopController.setAutoTone()
        local last,stable=nil,0
        for _=1,64 do
            LrTasks.sleep(0.25)
            if not isTarget() then error('自動校正期間選取照片已切換，停止處理。') end
            after=M.settings(photo)
            local current,changed={},false
            for key in pairs(tone) do
                current[key]=after[key]
                if not M.same(after[key],before[key]) then changed=true end
            end
            local signature=M.json(current)
            if signature==last then stable=stable+1 else stable=0;last=signature end
            if changed and stable>=4 then verified=true;break end
            -- Auto is idempotent: repeating it on an already-corrected photo is not
            -- evidence of success. Stop a stable no-change result after ~3 seconds.
            -- Slow/unobserved changes stay unconfirmed and never enter model analysis.
            if not changed and stable>=12 then break end
        end
        if verified then break end
    end
    if not verified then
        state.unverified=(state.unverified or 0)+1
    end
    local restore={}
    for key,value in pairs(before) do
        if not tone[key] and key~='ProcessVersion' and not M.same(after[key],value) then
            restore[key]=value
        end
    end
    for key,value in pairs(item.settings) do restore[key]=value end
    if next(restore) then
        local restored=false
        catalog:withWriteAccessDo('保留原色彩與銳利化',function()
            photo:applyDevelopSettings(restore,'保留原色彩與銳利化')
            restored=true
        end,{timeout=30})
        if not restored then error('自動校正後未取得保留設定的寫入權限；請查看步驟記錄。') end
    end
    state.toneResults=state.toneResults or {}
    state.toneResults[#state.toneResults+1]={photo_id=tostring(photo.localIdentifier),
        status=verified and 'changed_and_stable' or 'unchanged_or_unconfirmed',
        attempts=attempts,before=before,after=M.settings(photo)}
    if verified then
        state.applied=state.applied+1
        state.autoTone=(state.autoTone or 0)+1
    end
    return verified
end
