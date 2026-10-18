import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
from lupa.lua51 import LuaRuntime
PLUGIN=ROOT/'LightroomLocalDevelop.lrplugin'

class AutoTests(unittest.TestCase):
    def test_auto_apply_and_cancel(self):
        for answer,cancel,ready,expected,failed,unchanged in [('ok',False,1,1,0,False),('cancel',False,1,0,0,False),('ok',True,1,0,0,False),('ok',False,0,0,0,False),('ok',False,1,1,1,False),('ok',False,1,1,0,True)]:
            with self.subTest(answer=answer,cancel=cancel), tempfile.TemporaryDirectory(dir=None) as temp:
                folder=Path(temp)
                version=4 if failed else 3
                (folder/'local-result.tsv').write_text(f'LRRESULT\t{version}\t{ready}\t{ready}\t0\t{1-ready}\t0\t{failed}\n')
                (folder/'local-result').mkdir()
                (folder/'local-result/progress.tsv').write_text('LRPROGRESS\t2\t0\t1\tanalysing\t123\tDSC_123.NEF\t0\n')
                lua=LuaRuntime(unpack_returned_tuples=True)
                g=lua.globals(); g.folder=folder.as_posix();g.plugin=PLUGIN.as_posix();g.answer=answer;g.cancel=cancel
                g.unchanged=unchanged
                g.getCommon=lambda:lua.execute((PLUGIN/'Common.lua').read_text())
                g.getModel=lambda:lua.execute((PLUGIN/'ModelProgress.lua').read_text(encoding='utf-8'))
                g.getAutoCore=lambda:lua.execute((PLUGIN/'AutoCore.lua').read_text(encoding='utf-8'))
                lua.execute('''
                calls=0; exports=0; autoCalls=0; messages={}; commands={}; busy=false; deferred=nil; portions=0
                catalog={}; photo={localIdentifier=123}
                function photo:getRawMetadata() return 'D:/Photos/original.NEF' end
                current={Exposure2012=0,Sharpness=40}
                function photo:getDevelopSettings() return current end
                function catalog:getPath() return 'D:/catalog.lrcat' end
                function catalog:getTargetPhotos() return {photo} end
                function catalog:getTargetPhoto() return photo end
                function catalog:setSelectedPhotos(p,ps) assert(p==photo and #ps==1) end
                _PLUGIN={path=plugin}
                modules={
                  LrApplication={activeCatalog=function() return catalog end},
                  LrDialogs={confirm=function() return answer end,message=function(a,b) messages[#messages+1]={a,b} end,
                    showModalProgressDialog=function(opts)
                      assert(opts.functionContext and opts.cannotCancel==false)
                      modalCalls=(modalCalls or 0)+1
                      return modules.LrProgressScope()
                    end},
                  LrFunctionContext={callWithContext=function(n,f) f({}) end},
                  LrTasks={startAsyncTask=function(f)
                    if busy then deferred=f else busy=true;f();busy=false end
                  end,pcall=pcall,sleep=function()
                    if deferred then local task=deferred;deferred=nil;task() end
                  end,
                    execute=function(cmd) commands[#commands+1]=cmd; return 0 end},
                  LrPathUtils={child=function(a,b) if a:find('LightroomJobs',1,true) then a=folder end; return a..'/'..b end},
                  LrFileUtils={createAllDirectories=function() end},
                  LrProgressScope=function() return {setCaption=function() end,done=function() end,
                    setPortionComplete=function() portions=portions+1 end,
                    isCanceled=function() return cancel end} end
                }
                function import(n) return modules[n] end
                function dofile(path)
                  if path:match('Common.lua$') then return getCommon() end
                  if path:match('AutoCore.lua$') then return getAutoCore() end
                  if path:match('ModelProgress.lua$') then return getModel() end
                  if path:match('AutoToneCore.lua$') then return function(cat,p,item,state)
                    assert(exports==0 and calls==0);autoCalls=autoCalls+1;state.applied=state.applied+1;
                    state.autoTone=1;state.toneStarted=1;current.Exposure2012=0.4
                    if unchanged then state.applied=0;state.unchangedStable=1;current.Exposure2012=0 end
                    return true
                  end end
                  if path:match('ExportCore.lua$') then return function(opts)
                    assert(autoCalls==1)
                    assert(opts.stage==(unchanged and 'mixed-auto-and-current-develop' or 'after-lightroom-auto'))
                    assert(opts.stages['123']==(unchanged and 'current-develop' or 'after-lightroom-auto'))
                    assert(current.Exposure2012==(unchanged and 0 or 0.4))
                    assert(opts.photos[1]==photo and opts.catalog==catalog); exports=exports+1;return folder,1,0
                  end end
                  if path:match('ApplyCore.lua$') then return function(path,opts,state)
                    assert(opts.photos[1]==photo and opts.silent);calls=calls+1;state.applied=1
                    current.Exposure2012=0.6
                  end end
                  error('Unexpected module')
                end
                ''')
                lua.execute((PLUGIN/'Auto.lua').read_text(encoding='utf-8'))
                self.assertEqual(g.calls,expected)
                if unchanged:
                    self.assertIn('0 張已確認 Lightroom 基礎校正數值變更',g.messages[1][2])
                    self.assertIn('1 張自動後數值未變且穩定',g.messages[1][2])
                if failed:
                    self.assertEqual(g.messages[1][1], '本地修圖部分完成')
                    self.assertIn('1 張分析失敗', g.messages[1][2])
                if ready==0 and answer=='ok' and not cancel:
                    self.assertIn('1 張已確認 Lightroom 基礎校正數值變更',g.messages[1][2])
                    self.assertIn('0 張已套用 AI 微調',g.messages[1][2])
                    self.assertEqual(g.current['Exposure2012'],0.4)
                if expected:
                    self.assertEqual(g.modalCalls,1)
                    self.assertEqual(g.current['Exposure2012'],0.6)
                    self.assertGreater(g.portions,0)
                    job=json.loads((folder/'local-job.json').read_text(encoding='utf-8'))
                    self.assertEqual(job['batch'],folder.as_posix())
                    self.assertIn('RunLocal.ps1',g.commands[1])

if __name__=='__main__': unittest.main(verbosity=2)
