local LrApplication=import 'LrApplication'
local LrDialogs=import 'LrDialogs'
local LrTasks=import 'LrTasks'
local LrPathUtils=import 'LrPathUtils'
local LrFileUtils=import 'LrFileUtils'
local LrProgressScope=import 'LrProgressScope'
local M=dofile(LrPathUtils.child(_PLUGIN.path,'Common.lua'))
local export=dofile(LrPathUtils.child(_PLUGIN.path,'ExportCore.lua'))
local apply=dofile(LrPathUtils.child(_PLUGIN.path,'ApplyCore.lua'))
local runAutoTone=dofile(LrPathUtils.child(_PLUGIN.path,'AutoToneCore.lua'))
local runModel=dofile(LrPathUtils.child(_PLUGIN.path,'ModelProgress.lua'))
local resultDialog=dofile(LrPathUtils.child(_PLUGIN.path,'ResultDialog.lua'))
local function quoteArg(s)
    if s:find('[%%!"\r\n]') then error('Unsupported command path characters') end
    return '"'..s..'"'
end
local function normal(s) return s:gsub('\\','/'):lower():gsub('/+$','') end

return function(options)
options=options or {}
LrTasks.startAsyncTask(function()
    local state={applied=0}
    local progress
    local folder
    local catalog,photos,savedTarget
    local refine={applied=0}
    local ok,err=LrTasks.pcall(function()
        catalog=LrApplication.activeCatalog()
        photos=catalog:getTargetPhotos()
        savedTarget=catalog:getTargetPhoto()
        if #photos==0 then error('Select photos in Library first') end
        state.selected=#photos
        state.modifiedSkipped=0
        state.unreadableSkipped=0
        -- SDK application calls do not suppress Lightroom's own automatic metadata writing.
        local answer=LrDialogs.confirm('Catalog-only editing / 只修改編目',
            '先開啟「編目設定」>「中繼資料」，取消勾選「自動將變更寫入附屬檔案 (XMP/ACR)」。\n'..
            '此外掛無法替你可靠讀取或關閉此設定。只有確定已關閉才繼續。\n'..
            '只修改選取照片的顯影滑桿；不建立快照、不儲存中繼資料、不覆蓋原檔。',
            '已關閉，開始本地修圖','取消')
        if answer~='ok' then return end
        local root='C:\\AI\\LightroomJobs'
        for _,p in ipairs(photos) do
            local source=normal(p:getRawMetadata('path'))
            if source:sub(1,#normal(root)+1)==normal(root)..'/' then
                error('Original photos are inside the work folder. Move the work configuration, not the originals.')
            end
        end
        LrFileUtils.createAllDirectories(root)
        progress=LrProgressScope{title=options.onlyUnmodified and '本地修圖：僅未修改照片' or '本地修圖：全部選取照片'}
        local verifiedPhotos={}
        local stages={}
        local checkPath=LrPathUtils.child(root,'tone-check-'..os.date('%Y%m%d-%H%M%S')..'.json')
        for index,photo in ipairs(photos) do
            if progress:isCanceled() then error('已取消；已完成的 Lightroom 基礎校正仍保留，可查看步驟記錄。') end
            progress:setCaption('第 1 階段：Lightroom 自動校正 '..index..'/'..#photos..' 張')
            progress:setPortionComplete(index-1,#photos)
            local baseline=M.settings(photo)
            local zero,key=true,nil
            if options.onlyUnmodified then zero,key=M.hasZeroTone(baseline) end
            if zero then
                local prior=state.applied
                local eligible=runAutoTone(catalog,photo,{baseline=baseline,settings={}},state)
                if eligible then
                    verifiedPhotos[#verifiedPhotos+1]=photo
                    stages[tostring(photo.localIdentifier)]=state.applied>prior and 'after-lightroom-auto' or 'current-develop'
                end
            else
                if zero==false then state.modifiedSkipped=state.modifiedSkipped+1
                else state.unreadableSkipped=state.unreadableSkipped+1 end
                state.toneResults=state.toneResults or {}
                state.toneResults[#state.toneResults+1]={photo_id=tostring(photo.localIdentifier),attempts=0,
                    status=zero==false and 'modified_skipped' or 'tone_value_unavailable_skipped',
                    reason_key=key,before=baseline,after=baseline}
            end
            M.write(checkPath,M.json{version=1,confirmed=state.applied,unconfirmed=state.unverified or 0,
                unchanged_stable=state.unchangedStable or 0,selection_mode=options.onlyUnmodified and 'unmodified-only' or 'all',
                selected=state.selected,modified_skipped=state.modifiedSkipped,unreadable_skipped=state.unreadableSkipped,
                photos=state.toneResults or {}})
            if index%20==0 then LrTasks.sleep(0) end
        end
        if state.modifiedSkipped+state.unreadableSkipped==#photos then
            progress:done()
            resultDialog.show{allSkipped=true,onlyUnmodified=options.onlyUnmodified,selected=#photos,
                modified=state.modifiedSkipped,unreadable=state.unreadableSkipped,
                details='選取 '..#photos..' 張；已修改略過 '..state.modifiedSkipped..' 張；數值無法確認略過 '..state.unreadableSkipped..
                ' 張。\n未執行 LR 自動、預覽匯出或 AI 分析。\n檢查紀錄：'..checkPath}
            return
        end
        if #verifiedPhotos==0 then error('本次沒有確認穩定的顯影設定，未送入 AI。請檢查步驟記錄：'..checkPath) end
        catalog:setSelectedPhotos(savedTarget or photos[1],photos)
        progress:setCaption('Exporting selected previews / 準備分析預覽')
        local count,failed
        folder,count,failed=export{catalog=catalog,photos=verifiedPhotos,root=root,silent=true,progress=progress,
            stage=(state.unchangedStable or 0)>0 and 'mixed-auto-and-current-develop' or 'after-lightroom-auto',stages=stages}
        M.write(LrPathUtils.child(folder,'tone-verification.json'),M.json{version=1,confirmed=state.applied,
            unconfirmed=state.unverified or 0,unchanged_stable=state.unchangedStable or 0,
            selection_mode=options.onlyUnmodified and 'unmodified-only' or 'all',selected=state.selected,
            modified_skipped=state.modifiedSkipped,unreadable_skipped=state.unreadableSkipped,photos=state.toneResults or {}})
        if failed>0 then error('校正後預覽轉存失敗：'..failed..' 張；模型微調未套用，基礎校正已保留。') end
        if count==0 then error('No previews to analyse') end
        if progress:isCanceled() then error('已取消模型分析；Lightroom 基礎校正已保留。') end
        local jobPath=LrPathUtils.child(folder,'local-job.json')
        M.write(jobPath,M.json{batch=folder,stage='after-lightroom-auto'})
        progress:setCaption('Local model analysing; waiting / 本地模型分析中，請等待')
        local script=LrPathUtils.child(_PLUGIN.path,'RunLocal.ps1')
        local command='powershell.exe -NoProfile -ExecutionPolicy Bypass -File '..quoteArg(script)..' -Job '..quoteArg(jobPath)
        progress:done()
        progress=nil
        local code=runModel(folder,count,command)
        if code~=0 then error('本地模型微調失敗，基礎校正已保留。請查看 '..folder..'\\analysis.log') end
        -- The external process is not terminated by cancel. Cancellation still prevents apply.
        if LrApplication.activeCatalog():getPath()~=catalog:getPath() then error('Active catalog changed; apply stopped') end
        local f=assert(io.open(LrPathUtils.child(folder,'local-result.tsv'),'rb'))
        local result=f:read('*a'); f:close()
        local ready,modelJobs,policyJobs,unchanged,review,fail=
            result:match('^LRRESULT\t4\t(%d+)\t(%d+)\t(%d+)\t(%d+)\t(%d+)\t(%d+)')
        if not ready then
            ready,modelJobs,policyJobs,unchanged,review,fail=
                result:match('^LRRESULT\t3\t(%d+)\t(%d+)\t(%d+)\t(%d+)\t(%d+)\t(%d+)')
            if not ready or tonumber(fail)~=0 then error('Invalid analysis completion marker') end
        end
        progress=LrProgressScope{title='套用 AI 顯影滑桿',caption='本地分析完成，正在寫入編目設定'}
        if tonumber(ready)>0 then
            apply(LrPathUtils.child(folder,'local-result/plan.tsv'),{photos=verifiedPhotos,silent=true},refine)
        end
        progress:done()
        local summary='模式：'..(options.onlyUnmodified and '僅未修改照片' or '全部選取照片')..
            '；選取 '..state.selected..' 張。\n已修改略過 '..state.modifiedSkipped..
            ' 張；數值無法確認略過 '..state.unreadableSkipped..' 張。\n'..
            state.applied..' 張已確認 Lightroom 基礎校正數值變更。'..
            '\n'..(state.unchangedStable or 0)..' 張自動後數值未變且穩定，已以目前顯影設定接續 AI 分析。'..
            '\n'..(state.unverified or 0)..' 張控制／數值未確認，已略過後續處理。'..
            '\n'..modelJobs..' 張已套用 AI 微調；'..policyJobs..' 張已套用主體偏好規則（人像鮮豔度／銳利化，風景清晰度／去朦朧）。'..
            '\n'..unchanged..' 張無需額外 AI 微調；'..review..' 張模型判斷待確認。'..
            '\n'..fail..' 張分析失敗，已略過；其他成功計畫已照常處理。'..
            '\n依設定未建立快照。'
        resultDialog.show{onlyUnmodified=options.onlyUnmodified,selected=state.selected,analysed=count,
            autoChanged=state.applied,stableCurrent=state.unchangedStable,model=modelJobs,policy=policyJobs,
            modified=state.modifiedSkipped,unreadable=state.unreadableSkipped,unverified=state.unverified,
            review=review,failed=fail,
            details=summary..'\n工作資料夾：'..folder..'\n詳見 local-result/report.json。'}
    end)
    if catalog and photos and #photos>0 then
        LrTasks.pcall(function() catalog:setSelectedPhotos(savedTarget or photos[1],photos) end)
    end
    if not ok then
        if progress then progress:done() end
        LrTasks.sleep(0)
        LrDialogs.message('本地修圖已停止',tostring(err)..'\n已完成基礎校正：'..state.applied..
            '\n已完成模型微調：'..refine.applied..
            '\n已修改略過：'..(state.modifiedSkipped or 0)..' 張；數值無法確認略過：'..(state.unreadableSkipped or 0)..' 張。'..
            '\n自動色調呼叫次數（含重試）：'..(state.toneStarted or 0)..'；部分滑桿可能已變更。'..
            '\n數值未變且穩定：'..(state.unchangedStable or 0)..' 張；控制／數值未確認：'..(state.unverified or 0)..' 張。'..
            '\n未建立快照；需要時查看各張照片的步驟記錄。','critical')
    end
end)
end
