import json
from pathlib import Path
import tempfile
import unittest
from lupa.lua51 import LuaRuntime

PLUGIN=Path(__file__).resolve().parents[1]/'LightroomLocalDevelop.lrplugin'
KEYS=['Exposure2012','Contrast2012','Highlights2012','Shadows2012','Whites2012','Blacks2012']


class SelectionTests(unittest.TestCase):
    def test_exact_zero_filter_all_six_keys_and_unrelated_settings(self):
        lua=LuaRuntime(unpack_returned_tuples=True)
        common=lua.execute((PLUGIN/'Common.lua').read_text(encoding='utf-8'))
        baseline=dict.fromkeys(KEYS,0)
        baseline.update(Sharpness=40,Temperature=6000,Vibrance=11,Clarity2012=20)
        self.assertIs(common.hasZeroTone(lua.table_from(baseline)),True)
        for key in KEYS:
            for value in [.00000001,-.01,10]:
                self.assertEqual(common.hasZeroTone(lua.table_from(dict(baseline,**{key:value}))),(False,key))
            for value in [None,True,'0',float('nan'),float('inf')]:
                with self.subTest(key=key,value=value):
                    self.assertEqual(common.hasZeroTone(lua.table_from(dict(baseline,**{key:value}))),(None,key))

    def test_filter_precedes_all_changes_and_excludes_photos_from_both_stages(self):
        for mode in ['mixed','all','all-skipped']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                folder=Path(temp)
                (folder/'local-result.tsv').write_text('LRRESULT\t4\t2\t1\t1\t0\t0\t0\n')
                lua=LuaRuntime(unpack_returned_tuples=True);g=lua.globals()
                g.folder=folder.as_posix();g.plugin=PLUGIN.as_posix();g.mode=mode
                g.common=lambda:lua.execute((PLUGIN/'Common.lua').read_text(encoding='utf-8'))
                g.core=lambda:lua.execute((PLUGIN/'AutoCore.lua').read_text(encoding='utf-8'))
                lua.execute('''
                _PLUGIN={path=plugin};messages={};autoIDs={};exportIDs={};applyIDs={};modelCalls=0
                photos={}
                for i=1,5 do
                  local p={localIdentifier=i,settings={Exposure2012=0,Contrast2012=0,Highlights2012=0,
                    Shadows2012=0,Whites2012=0,Blacks2012=0,Sharpness=40,Temperature=6000}}
                  function p:getDevelopSettings() return self.settings end
                  function p:getRawMetadata() return 'D:/Photos/'..self.localIdentifier..'.NEF' end
                  photos[i]=p
                end
                photos[2].settings.Exposure2012=.01
                photos[3].settings.Shadows2012=-20
                photos[4].settings.Contrast2012=nil
                photos[5].settings.Vibrance=15
                if mode=='all-skipped' then
                  photos[1].settings.Highlights2012=-1;photos[5].settings.Blacks2012=-1
                end
                catalog={};target=photos[2]
                function catalog:getTargetPhotos() return photos end
                function catalog:getTargetPhoto() return target end
                function catalog:getPath() return 'test.lrcat' end
                function catalog:setSelectedPhotos(p,ps) assert(#ps==5 and p==photos[2]) end
                modules={
                  LrApplication={activeCatalog=function() return catalog end},
                  LrDialogs={confirm=function() return 'ok' end,
                    message=function(a,b) messages[#messages+1]={a,b} end},
                  LrTasks={startAsyncTask=function(f) f() end,pcall=pcall,sleep=function() end},
                  LrPathUtils={child=function(a,b)
                    if a:find('LightroomJobs',1,true) then a=folder end
                    return a..'/'..b
                  end},
                  LrFileUtils={createAllDirectories=function() end},
                  LrProgressScope=function() return {done=function() end,setCaption=function() end,
                    setPortionComplete=function() end,isCanceled=function() return false end} end
                }
                function import(n) return modules[n] end
                function dofile(path)
                  if path:match('Common.lua$') then return common() end
                  if path:match('AutoCore.lua$') then return core() end
                  if path:match('AutoToneCore.lua$') then return function(cat,p,item,state)
                    autoIDs[#autoIDs+1]=p.localIdentifier
                    state.applied=state.applied+1;p.settings.Exposure2012=.5
                    return true
                  end end
                  if path:match('ExportCore.lua$') then return function(opts)
                    for _,p in ipairs(opts.photos) do exportIDs[#exportIDs+1]=p.localIdentifier end
                    return folder,#opts.photos,0
                  end end
                  if path:match('ModelProgress.lua$') then return function() modelCalls=modelCalls+1;return 0 end end
                  if path:match('ApplyCore.lua$') then return function(path,opts,state)
                    for _,p in ipairs(opts.photos) do applyIDs[#applyIDs+1]=p.localIdentifier end
                    state.applied=#opts.photos
                  end end
                  error('Unexpected module '..path)
                end
                ''')
                entry='Auto.lua' if mode=='all' else 'AutoUnmodified.lua'
                lua.execute((PLUGIN/entry).read_text(encoding='utf-8'))
                expected=[] if mode=='all-skipped' else list(range(1,6)) if mode=='all' else [1,5]
                for value in [g.autoIDs,g.exportIDs,g.applyIDs]:
                    self.assertEqual(list(value.values()),expected)
                self.assertEqual(g.modelCalls,0 if mode=='all-skipped' else 1)
                if mode!='all':
                    self.assertEqual(g.photos[2].settings.Exposure2012,.01)
                    self.assertEqual(g.photos[3].settings.Shadows2012,-20)
                    self.assertIsNone(g.photos[4].settings.Contrast2012)
                    if mode=='mixed':
                        audit=json.loads((folder/'tone-verification.json').read_text(encoding='utf-8'))
                        self.assertEqual(audit['selected'],5)
                        self.assertEqual(audit['modified_skipped'],2)
                        self.assertEqual(audit['unreadable_skipped'],1)
                    else:
                        self.assertEqual(g.messages[1][1],'本地修圖：沒有符合條件的照片')
                        self.assertFalse((folder/'local-job.json').exists())


if __name__=='__main__':unittest.main()
