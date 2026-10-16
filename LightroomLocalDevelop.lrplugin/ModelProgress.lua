local LrDialogs=import 'LrDialogs'
local LrFunctionContext=import 'LrFunctionContext'
local LrTasks=import 'LrTasks'
local LrPathUtils=import 'LrPathUtils'
local M=dofile(LrPathUtils.child(_PLUGIN.path,'Common.lua'))

return function(folder,count,command)
    local code,executeError,finished
    LrFunctionContext.callWithContext('LocalToneAIModelProgress',function(context)
        local progress=LrDialogs.showModalProgressDialog{
            title='第 2 階段：本地 AI 分析',caption='準備本地模型，尚未套用 AI 滑桿',
            functionContext=context,cannotCancel=false}
        progress:setPortionComplete(0,count)
        -- Let Lightroom draw the dialog before launching the worker.
        LrTasks.sleep(0)
        if progress:isCanceled() then error('已取消模型分析；基礎校正已保留。') end
        LrTasks.startAsyncTask(function()
            local ok,value=LrTasks.pcall(function() return LrTasks.execute(command) end)
            if ok then code=value else executeError=value end
            finished=true
        end)
        local started=os.time()
        local completed,total,stage,name,failed=0,count,'starting','',0
        while not finished do
            if progress:isCanceled() then
                error('已取消模型微調套用；基礎校正已保留。背景分析可能仍在完成，不會由本次流程套用。')
            end
            local pf=io.open(LrPathUtils.child(folder,'local-result/progress.tsv'),'rb')
            if pf then
                local line=pf:read('*a');pf:close()
                local d,t,s,id,n,f=line:match('^LRPROGRESS\t2\t(%d+)\t(%d+)\t([^\t\r\n]+)\t([^\t\r\n]*)\t([^\t\r\n]*)\t(%d+)')
                if not d then d,t,s=line:match('^LRPROGRESS\t1\t(%d+)\t(%d+)\t([^\t\r\n]+)') end
                if d and tonumber(t)==count and tonumber(d)<=count and tonumber(d)>=completed then
                    completed,total,stage,name,failed=tonumber(d),tonumber(t),s,n and M.decode(n) or '',tonumber(f) or 0
                end
            end
            local task=stage=='starting' and '準備模型' or stage=='compiling' and '整理修圖計畫' or
                stage=='complete' and '分析完成，等待套用' or name~='' and name or '準備下一張'
            progress:setPortionComplete(completed,total)
            progress:setCaption('已分析 '..completed..'/'..total..' ('..math.floor(completed*100/total)..'%) | '..
                task..' | '..math.max(0,os.time()-started)..'秒 | 失敗 '..failed)
            LrTasks.sleep(1)
        end
        if progress:isCanceled() then error('已取消模型微調套用；基礎校正已保留。') end
        progress:done()
    end)
    -- Windows may need a UI tick after the modal context closes.
    LrTasks.sleep(0)
    if executeError then error(tostring(executeError)) end
    return code
end
