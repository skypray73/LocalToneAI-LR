local M = {}
M.ranges = {
    Exposure2012={-5,5}, Temperature={2000,50000}, Tint={-150,150},
    Sharpness={0,150}, SharpenRadius={0.5,3},
}
for _, k in ipairs({'Contrast2012','Highlights2012','Shadows2012','Whites2012','Blacks2012',
    'Texture','Clarity2012','Dehaze','Vibrance','Saturation','RelativeTemperature','RelativeTint'}) do
    M.ranges[k]={-100,100}
end
for _, k in ipairs({'SharpenDetail','SharpenEdgeMasking','LuminanceSmoothing','ColorNoiseReduction'}) do
    M.ranges[k]={0,100}
end
function M.encode(s)
    return (tostring(s):gsub('[^%w%-_%.~]', function(c) return string.format('%%%02X',string.byte(c)) end))
end
function M.decode(s)
    return (s:gsub('%%(%x%x)', function(x) return string.char(tonumber(x,16)) end))
end
function M.quote(s)
    local escapes = {['"']='\\"', ['\\']='\\\\', ['\n']='\\n', ['\r']='\\r', ['\t']='\\t'}
    return '"' .. tostring(s):gsub('[%z\1-\31\\"]', function(c)
        return escapes[c] or string.format('\\u%04x', string.byte(c))
    end) .. '"'
end
function M.json(v)
    local t=type(v)
    if t=='nil' then return 'null' end
    if t=='string' then return M.quote(v) end
    if t=='boolean' then return v and 'true' or 'false' end
    if t=='number' then
        if v~=v or v==math.huge or v==-math.huge then return 'null' end
        return string.format('%.15g',v)
    end
    if t=='table' then
        local keys={}
        for k in pairs(v) do keys[#keys+1]=k end
        table.sort(keys, function(a,b) return tostring(a)<tostring(b) end)
        local out={}
        for _,k in ipairs(keys) do out[#out+1]=M.quote(k)..':'..M.json(v[k]) end
        return '{'..table.concat(out,',')..'}'
    end
    error('Unsupported JSON type: '..t)
end
function M.array(items)
    local out={}
    for i,v in ipairs(items) do out[i]=M.json(v) end
    return '['..table.concat(out,',')..']'
end
function M.write(path, data)
    local f,err=io.open(path,'wb')
    if not f then error(err) end
    local ok,msg=f:write(data)
    f:close()
    if not ok then error(msg) end
end
function M.settings(photo)
    local all=photo:getDevelopSettings()
    local out={}
    for k in pairs(M.ranges) do
        if type(all[k])=='number' then out[k]=all[k] end
    end
    if type(all.WhiteBalance)=='string' then out.WhiteBalance=all.WhiteBalance end
    if type(all.ProcessVersion)=='string' then out.ProcessVersion=all.ProcessVersion end
    return out
end
function M.same(a,b)
    if type(a)=='number' and type(b)=='number' then return math.abs(a-b)<0.000001 end
    return a==b
end
-- Exact zero is intentional: even tiny non-zero values count as edited.
function M.hasZeroTone(settings)
    for _,key in ipairs({'Exposure2012','Contrast2012','Highlights2012','Shadows2012','Whites2012','Blacks2012'}) do
        local value=settings[key]
        if type(value)~='number' or value~=value or value==math.huge or value==-math.huge then
            return nil,key
        end
        if value~=0 then return false,key end
    end
    return true
end
function M.readPlan(path)
    local f,err=io.open(path,'rb')
    if not f then error(err) end
    local data=f:read('*a'); f:close()
    local catalog,items,order=nil,{},{}
    for line in data:gmatch('[^\r\n]+') do
        if not catalog then
            local version,encoded=line:match('^LRPLAN\t(%d+)\t([^\t]+)$')
            if version~='1' then error('Invalid plan header') end
            catalog=M.decode(encoded)
        else
            local id,p,k,v,b=line:match('^(%d+)\t([^\t]+)\t([^\t]+)\t([^\t]+)\t([^\t]+)$')
            if not id then error('Invalid plan row') end
            p,v,b=M.decode(p),M.decode(v),M.decode(b)
            local guard=k:match('^Guard_(.+)$')
            if guard then
                if not M.ranges[guard] then error('Unsupported guard') end
                k=guard
            end
            local action=k=='Action_AutoTone'
            if action then
                if v~='1' or b~='1' then error('Invalid auto tone action') end
            elseif k=='WhiteBalance' then
                if v~='Custom' then error('Only Custom WB supported') end
            else
                local r=M.ranges[k]
                v,b=tonumber(v),tonumber(b)
                if not r or not v or not b or v~=v or b~=b or
                    v<r[1] or v>r[2] or b==math.huge or b==-math.huge then
                    error('Invalid value or unsupported setting: '..k)
                end
            end
            if not items[id] then
                items[id]={id=id,path=p,settings={},baseline={},seen={}}; order[#order+1]=id
            end
            local item=items[id]
            local rowKey=(guard and 'Guard_' or '')..k
            if item.path~=p or item.seen[rowKey] or (item.baseline[k]~=nil and not M.same(item.baseline[k],b)) then
                error('Duplicate or conflicting plan row')
            end
            item.seen[rowKey]=true
            if action then
                item.autoTone=true
            elseif guard then
                if not M.same(v,b) then error('Guard cannot change settings') end
            else
                item.settings[k]=v
            end
            if not action then item.baseline[k]=b end
        end
    end
    if not catalog or #order==0 then error('Plan has no adjustments') end
    for _,id in ipairs(order) do
        if not next(items[id].settings) and not items[id].autoTone then error('Guard-only item has no adjustments') end
    end
    return catalog,items,order
end
return M
