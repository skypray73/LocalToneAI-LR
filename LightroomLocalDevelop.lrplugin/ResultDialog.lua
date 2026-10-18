local LrDialogs=import 'LrDialogs'
local LrView=import 'LrView'
local R={}

function R.build(data)
    local function number(key) return tonumber(data[key]) or 0 end
    local completed=math.max(0,number('analysed')-number('review')-number('failed'))
    local attention=number('review')+number('failed')+number('unreadable')+number('unverified')
    local lines={}
    local function add(key,label)
        if number(key)>0 then lines[#lines+1]=label..'：'..number(key)..' 張' end
    end
    local title,headline,footer
    if data.allSkipped then
        title='沒有需要處理的照片'
        headline='本次未修改照片'
        footer=attention>0 and '請先確認無法讀取設定的照片。' or '如需重新修圖，可選擇「全部」模式。'
    else
        title=attention>0 and '修圖完成，部分照片需查看' or '修圖完成'
        headline='已完成 '..completed..' 張照片'
        footer=completed>0 and '請到「編輯相片」查看效果。' or '請查看需要確認的照片與詳細紀錄。'
        -- These are overlapping action counts, not a partition of completed photos.
        add('autoChanged','LR 自動校正')
        add('stableCurrent','沿用目前亮暗設定')
        add('model','AI 亮暗微調')
        add('policy','人像／風景調整')
        if number('model')==0 and completed>0 then
            lines[#lines+1]='AI 本次未追加亮暗微調。'
        end
    end
    add('modified','略過已修改照片')
    add('unreadable','無法讀取設定，已略過')
    add('unverified','LR 校正未確認，已略過')
    add('review','需要手動確認')
    if number('failed')>0 then
        lines[#lines+1]='AI 分析失敗：'..number('failed')..' 張（先前調整已保留）'
    end
    return {title=title,headline=headline,lines=lines,footer=footer,
        mode=(data.onlyUnmodified and '僅處理未修改照片' or '處理全部選取照片')..' · 選取 '..number('selected')..' 張',
        completed=completed,attention=attention}
end

function R.show(data)
    local result=R.build(data)
    local f=LrView.osFactory()
    local rows={spacing=f:control_spacing(),
        f:static_text{title=result.headline,font='<system/bold>',width=440,height_in_lines=-1},
        f:static_text{title=result.mode,font='<system/small>',width=440,height_in_lines=-1},
        f:separator{fill_horizontal=1}}
    for _,line in ipairs(result.lines) do
        rows[#rows+1]=f:static_text{title=line,width=440,height_in_lines=-1}
    end
    rows[#rows+1]=f:separator{fill_horizontal=1}
    rows[#rows+1]=f:static_text{title=result.footer,width=440,height_in_lines=-1}
    repeat
        local answer=LrDialogs.presentModalDialog{title=result.title,contents=f:column(rows),
            actionVerb='完成',cancelVerb='< exclude >',otherVerb='查看詳細紀錄'}
        if answer~='other' then break end
        LrDialogs.message('詳細處理紀錄',data.details or '本次沒有其他紀錄。','info')
    until false
end

return R
