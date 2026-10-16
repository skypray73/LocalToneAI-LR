local LrApplication=import 'LrApplication'
local LrDialogs=import 'LrDialogs'
local LrTasks=import 'LrTasks'
local LrPathUtils=import 'LrPathUtils'
local LrFileUtils=import 'LrFileUtils'
local LrExportSession=import 'LrExportSession'
local M=dofile(LrPathUtils.child(_PLUGIN.path,'Common.lua'))

return function(options)
    options=options or {}

        local catalog=options.catalog or LrApplication.activeCatalog()
        local selected=options.photos or catalog:getTargetPhotos()
        if #selected==0 then error('Select photos first') end
        local root=options.root
        if not root then
            local chosen=LrDialogs.runOpenPanel{title='Choose analysis output folder',canChooseFiles=false,
                canChooseDirectories=true,allowsMultipleSelection=false}
            if not chosen then return end
            root=chosen[1]
        end
        local folder=LrPathUtils.child(root,'local-batch-'..os.date('%Y%m%d-%H%M%S'))
        if LrFileUtils.exists(folder) then error('Batch folder already exists; try again in a moment') end
        LrFileUtils.createAllDirectories(LrPathUtils.child(folder,'previews'))
        local photos,failures={},{}
        for index,photo in ipairs(selected) do
            if options.progress then
                if options.progress:isCanceled() then error('已取消預覽匯出，未套用設定。') end
                options.progress:setCaption('準備第 '..index..'/'..#selected..' 張預覽')
                options.progress:setPortionComplete(index-1,#selected)
            end
            local id=tostring(photo.localIdentifier)
            local jpeg,failure=nil,nil
            local baseline=M.settings(photo)
            -- Fresh develop rendering; cached requestJpegThumbnail can return a blank JPEG.
            -- Each export destination is a new folder, never a source photo folder.
            local renderFolder=LrPathUtils.child(folder,'rendered/'..id)
            LrFileUtils.createAllDirectories(renderFolder)
            local session=LrExportSession{
                photosToExport={photo},
                exportSettings={
                    LR_exportServiceProvider='com.adobe.ag.export.file',
                    LR_export_destinationType='specificFolder',
                    LR_export_destinationPathPrefix=renderFolder,
                    LR_export_useSubfolder=false,
                    LR_format='JPEG', LR_jpeg_quality=0.9,
                    LR_export_colorSpace='sRGB', LR_extensionCase='lowercase',
                    LR_size_doConstrain=true, LR_size_doNotEnlarge=true,
                    LR_size_resizeType='wh', LR_size_maxWidth=1024, LR_size_maxHeight=1024,
                    LR_size_units='pixels', LR_size_resolution=72, LR_size_resolutionUnits='inch',
                    LR_outputSharpeningOn=false, LR_useWatermark=false,
                    LR_reimportExportedPhoto=false, LR_reimport_stackWithOriginal=false,
                    LR_renamingTokensOn=false, LR_collisionHandling='rename',
                    LR_minimizeEmbeddedMetadata=true, LR_removeLocationMetadata=true,
                },
            }
            for _,rendition in session:renditions() do
                local success,pathOrMessage=rendition:waitForRender()
                if success then
                    local function normalized(s) return s:gsub('\\','/'):lower():gsub('/+$','') end
                    if normalized(pathOrMessage):sub(1,#normalized(renderFolder)+1)~=normalized(renderFolder)..'/' then
                        error('Renderer returned a path outside the new work folder; stopped')
                    end
                    local f,why=io.open(pathOrMessage,'rb')
                    if f then jpeg=f:read('*a'); f:close() else failure=why end
                else failure=pathOrMessage end
            end
            if type(jpeg)=='string' and jpeg:sub(1,2)==string.char(255,216) then
                local after=M.settings(photo)
                if M.json(after)~=M.json(baseline) then
                    failures[#failures+1]={photo_id=id,error='Settings changed while preview was generated'}
                else
                    M.write(LrPathUtils.child(folder,'previews/'..id..'.jpg'),jpeg)
                    photos[#photos+1]={photo_id=id,path=photo:getRawMetadata('path'),
                        preview='previews/'..id..'.jpg',file_format=photo:getRawMetadata('fileFormat'),
                        pipeline_stage=options.stages and options.stages[id] or options.stage or 'current-develop',
                        iso=photo:getRawMetadata('isoSpeedRating'),settings=baseline}
                end
            else
                failures[#failures+1]={photo_id=id,error=tostring(failure or 'Rendered preview missing/invalid JPEG')}
            end
        end
        local data='{"version":1,"catalog":'..M.quote(catalog:getPath())..
            ',"pipeline_stage":'..M.quote(options.stage or 'current-develop')..
            ',"photos":'..M.array(photos)..',"failures":'..M.array(failures)..'}'
        M.write(LrPathUtils.child(folder,'manifest.json'),data)
        if not options.silent then
            LrDialogs.message('Local export complete',#photos..' previews; '..#failures..' failures.\n'..folder,'info')
        end
        return folder,#photos,#failures
end
