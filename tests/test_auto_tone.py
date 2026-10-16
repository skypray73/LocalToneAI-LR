from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
from lupa.lua51 import LuaRuntime
PLUGIN=ROOT/'LightroomLocalDevelop.lrplugin'

class AutoToneTests(unittest.TestCase):
    def test_auto_waits_for_changes_without_repeating_noops(self):
        for mode in ('noop','delayed','too-late','unstable','bad-control'):
            lua=LuaRuntime(unpack_returned_tuples=True)
            g=lua.globals();g.plugin=PLUGIN.as_posix();g.mode=mode
            lua.execute('''
            _PLUGIN={path=plugin};current={Exposure2012=0,Contrast2012=0,Highlights2012=0,Shadows2012=0,Whites2012=0,Blacks2012=0,Vibrance=0,Saturation=0,Sharpness=40}
            photo={localIdentifier=123};catalog={};calls=0;ticks=0
            function photo:getDevelopSettings() return current end
            function photo:applyDevelopSettings(s) for k,v in pairs(s) do current[k]=v end end
            function catalog:setSelectedPhotos(p,ps) end
            function catalog:getTargetPhoto() return photo end
            function catalog:withWriteAccessDo(n,f) f() end
            modules={LrPathUtils={child=function(a,b) return a..'/'..b end},
              LrTasks={pcall=pcall,sleep=function()
                ticks=ticks+1
                if mode=='delayed' and calls>0 and ticks>8 then current.Shadows2012=48 end
                if mode=='too-late' and calls>0 and ticks>32 then current.Shadows2012=48 end
                if mode=='unstable' and calls>0 then current.Shadows2012=ticks%2 end
              end},
              LrApplicationView={switchToModule=function() end},
              LrDevelopController={getValue=function(k)
                if k=='Exposure' then return mode=='bad-control' and 1 or current.Exposure2012 end
                return nil
              end,
                setAutoTone=function() calls=calls+1;if mode=='retry' and calls==2 then current.Shadows2012=50 end end}}
            function import(n) return modules[n] end
            state={applied=0};item={settings={},baseline={Exposure2012=0,Sharpness=40}}
            ''')
            run=lua.execute((PLUGIN/'AutoToneCore.lua').read_text(encoding='utf-8'))
            verified=run(g.catalog,g.photo,g.item,g.state)
            unconfirmed=mode in ('unstable','bad-control')
            unchanged=mode in ('noop','too-late')
            self.assertEqual(bool(verified),not unconfirmed)
            self.assertEqual(g.state['applied'],1 if mode=='delayed' else 0)
            self.assertEqual(g.calls,0 if mode=='bad-control' else 1)
            if mode=='noop':
                self.assertLessEqual(g.ticks,15)
            if unconfirmed:self.assertEqual(g.state['unverified'],1)
            if unchanged:
                self.assertEqual(g.state['unchangedStable'],1)
                self.assertIsNone(g.state['unverified'])
                self.assertEqual(g.state['toneResults'][1]['status'],'unchanged_stable_current')

    def test_native_auto_tone_preserves_colour_and_sharpening(self):
        for portrait in (False,True):
            lua=LuaRuntime(unpack_returned_tuples=True)
            g=lua.globals();g.plugin=PLUGIN.as_posix();g.portrait=portrait
            lua.execute('''
            _PLUGIN={path=plugin}
            current={Exposure2012=0,Contrast2012=0,Highlights2012=0,Shadows2012=0,Whites2012=0,Blacks2012=0,
                Vibrance=7,Saturation=2,Sharpness=40,SharpenRadius=1,SharpenDetail=25,SharpenEdgeMasking=0}
            photo={};catalog={};snapshots=0;autoCalls=0
            function photo:getDevelopSettings() return current end
            function photo:createDevelopSnapshot() assert(autoCalls==0);snapshots=snapshots+1 end
            function photo:applyDevelopSettings(s) for k,v in pairs(s) do current[k]=v end end
            function catalog:setSelectedPhotos(p,ps) assert(p==photo and #ps==1) end
            function catalog:getTargetPhoto() return photo end
            function catalog:withWriteAccessDo(n,f) f() end
            modules={
              LrPathUtils={child=function(a,b) return a..'/'..b end},
              LrTasks={pcall=pcall,sleep=function() end},
              LrApplicationView={switchToModule=function(n) assert(n=='develop') end},
              LrDevelopController={getValue=function(k) return current[k] end,
                setAutoTone=function()
                  autoCalls=autoCalls+1
                  current.Exposure2012=0.4;current.Contrast2012=12;current.Shadows2012=35
                  current.Vibrance=30;current.Saturation=9;current.Sharpness=80
                end}
            }
            function import(n) return modules[n] end
            state={applied=0,snapshot='test snapshot'}
            item={settings=portrait and {Sharpness=0} or {},baseline={Exposure2012=0,Sharpness=40}}
            ''')
            run=lua.execute((PLUGIN/'AutoToneCore.lua').read_text(encoding='utf-8'))
            run(g.catalog,g.photo,g.item,g.state)
            self.assertEqual(g.current['Exposure2012'],0.4)
            self.assertEqual(g.current['Contrast2012'],12)
            self.assertEqual(g.current['Vibrance'],30)
            self.assertEqual(g.current['Saturation'],9)
            self.assertEqual(g.current['Sharpness'],0 if portrait else 40)
            self.assertEqual(g.snapshots,0)
            self.assertEqual(g.state['applied'],1)

if __name__=='__main__':unittest.main(verbosity=2)
