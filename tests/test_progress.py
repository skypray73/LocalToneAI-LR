from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote
from lupa.lua51 import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analyze_local import write_progress
PLUGIN=ROOT/'LightroomLocalDevelop.lrplugin'


class ProgressTests(unittest.TestCase):
    def test_progress_writer_encodes_only_basename_and_survives_locked_file(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            write_progress(folder,1,3,'analysing',{'photo_id':'12','path':'D:\\private\\人像\t01.NEF'},1)
            original=(folder/'progress.tsv').read_bytes()
            fields=original.decode().rstrip('\n').split('\t')
            self.assertEqual(len(fields),8)
            self.assertEqual(unquote(fields[6]),'人像\t01.NEF')
            self.assertNotIn('private',original.decode())
            with patch.object(Path,'replace',side_effect=PermissionError('reader lock')):
                write_progress(folder,2,3,'between-photos')
            self.assertEqual((folder/'progress.tsv').read_bytes(),original)
            write_progress(folder,3,3,'complete',failed=1)
            self.assertIn('\t3\t3\tcomplete\t\t\t1', (folder/'progress.tsv').read_text())

    def test_visible_progress_and_cancellation_cleanup(self):
        for mode in ('normal','cancel-before','cancel-after','execute-error','v1','partial'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                folder=Path(temp);(folder/'local-result').mkdir()
                record='LRPROGRESS\t2\t1\t2\tanalysing\t12\tDSC_0012.NEF\t1\n'
                if mode=='v1':record='LRPROGRESS\t1\t1\t2\tanalysing\n'
                if mode=='partial':record='LRPROGRESS\t2\t1'
                (folder/'local-result/progress.tsv').write_text(record)
                lua=LuaRuntime(unpack_returned_tuples=True);g=lua.globals()
                g.mode=mode;g.folder=folder.as_posix();g.plugin=PLUGIN.as_posix()
                g.common=lambda:lua.execute((PLUGIN/'Common.lua').read_text(encoding='utf-8'))
                lua.execute('''
                _PLUGIN={path=plugin};captions={};ticks=0;executions=0;closed=false
                modules={
                  LrPathUtils={child=function(a,b) return a..'/'..b end},
                  LrFunctionContext={callWithContext=function(n,f)
                    local ok,res=pcall(f,{});closed=true;if not ok then error(res) end
                  end},
                  LrDialogs={showModalProgressDialog=function(opts)
                    assert(opts.title=='第 2 階段：本地 AI 分析' and opts.functionContext)
                    return {done=function() end,setPortionComplete=function(s,d,t) done,total=d,t end,
                      setCaption=function(s,c) captions[#captions+1]=c end,
                      isCanceled=function() return mode=='cancel-before' or mode=='cancel-after' and ticks>=2 end}
                  end},
                  LrTasks={pcall=pcall,startAsyncTask=function(f) worker=f end,
                    sleep=function() ticks=ticks+1;if worker then local f=worker;worker=nil;f() end end,
                    execute=function() executions=executions+1;if mode=='execute-error' then error('worker failed') end;return 0 end}
                }
                function import(n) return modules[n] end
                function dofile(p) return common() end
                ''')
                run=lua.execute((PLUGIN/'ModelProgress.lua').read_text(encoding='utf-8'))
                if mode.startswith('cancel') or mode=='execute-error':
                    with self.assertRaises(Exception):run(g.folder,2,'test command')
                else:
                    self.assertEqual(run(g.folder,2,'test command'),0)
                    caption=g.captions[1]
                    self.assertIn('已分析 '+('0/2' if mode=='partial' else '1/2'),caption)
                    if mode=='normal':
                        self.assertIn('DSC_0012.NEF',caption)
                        self.assertIn('50%',caption)
                        self.assertIn('失敗 1',caption)
                self.assertTrue(g.closed)
                self.assertEqual(g.executions,0 if mode=='cancel-before' else 1)


if __name__=='__main__':unittest.main()
