import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
from lupa.lua51 import LuaRuntime
spec = importlib.util.spec_from_file_location('build_plan', ROOT / 'scripts/build_plan.py')
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)
PLUGIN = ROOT / 'LightroomLocalDevelop.lrplugin'


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {'version': 1, 'catalog': 'C:\\測試\\catalog.lrcat', 'photos': [
            {'photo_id': '123', 'path': 'C:\\照片\\a.NEF', 'file_format': 'RAW',
             'settings': {'Exposure2012': 0.6, 'Highlights2012': 0, 'Vibrance': 0, 'Sharpness': 40, 'SharpenRadius': 1,
                          'SharpenDetail': 25, 'SharpenEdgeMasking': 0, 'WhiteBalance': 'As Shot',
                          'Temperature': 5200, 'Tint': 5, 'Clarity2012':0, 'Dehaze':0}},
            {'photo_id': '124', 'path': 'C:\\照片\\b.NEF', 'file_format': 'RAW',
             'settings': {'Exposure2012': 0, 'Highlights2012': 0, 'Vibrance': 0, 'Clarity2012':0, 'Dehaze':0}}]}
        self.decisions = {'style': '自然', 'photos': [
            {'photo_id': '123', 'path': 'C:\\照片\\a.NEF', 'reason': '主體略暗',
             'subject': 'landscape', 'confidence': 'medium', 'status': 'ready',
             'settings': {'Exposure2012': 0.9, 'Highlights2012': -25}}]}
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.common = self.lua.execute((PLUGIN / 'Common.lua').read_text(encoding='utf-8'))

    def plan(self, decisions=None):
        return bp.compile_plan(self.manifest, decisions or self.decisions)

    def test_xmp_and_matching_roundtrip(self):
        plan, presets, report = self.plan()
        with tempfile.TemporaryDirectory(dir=None) as tmp:
            path = Path(tmp) / 'plan.tsv'
            path.write_text(plan, encoding='utf-8')
            catalog, items, order = self.common.readPlan(str(path))
            self.assertEqual(catalog, self.manifest['catalog'])
            self.assertEqual(items['123']['path'], self.manifest['photos'][0]['path'])
            self.assertEqual(items['123']['baseline']['Exposure2012'], 0.6)
            self.assertEqual(items['123']['settings']['Exposure2012'], 0.9)
            tree = ET.fromstring(presets['123'])
            desc = tree.find(f'.//{{{bp.RDF}}}Description')
            self.assertEqual(desc.attrib[f'{{{bp.CRS}}}Highlights2012'], '-25')
            self.assertNotIn(f'{{{bp.CRS}}}ProcessVersion', desc.attrib)
            self.assertEqual(report['unanalysed'], ['124'])

    def test_reject_bad_inputs(self):
        for bad in [float('nan'), float('inf'), True, 6, '0.3']:
            d = copy.deepcopy(self.decisions)
            d['photos'][0]['settings'] = {'Exposure2012': bad}
            with self.assertRaises(ValueError):
                self.plan(d)
        for changes in [{'settings': {'AI_Denoise': 50}}, {'path': 'C:\\other\\a.NEF'},
                        {'settings': {'RelativeTemperature': 10, 'WhiteBalance': 'Custom'}}]:
            d = copy.deepcopy(self.decisions)
            d['photos'][0].update(changes)
            with self.assertRaises(ValueError):
                self.plan(d)
        d = copy.deepcopy(self.decisions)
        d['photos'].append(d['photos'][0])
        with self.assertRaises(ValueError):
            self.plan(d)

    def test_review_and_white_balance(self):
        d = copy.deepcopy(self.decisions)
        d['photos'][0]['confidence'] = 'low'
        self.assertEqual(len(self.plan(d)[1]), 0)
        self.assertEqual(len(bp.compile_plan(self.manifest, d, True)[1]), 1)
        d['photos'][0]['confidence'] = 'high'
        d['photos'][0]['settings'] = {'WhiteBalance': 'Custom', 'Temperature': 5400}
        plan = self.plan(d)[0]
        self.assertIn('WhiteBalance\tCustom\tAs%20Shot', plan)
        d['photos'][0]['settings'].pop('WhiteBalance')
        with self.assertRaises(ValueError):
            self.plan(d)

    def test_lua_syntax_and_json(self):
        loadfile = self.lua.eval('loadfile')
        for file in PLUGIN.glob('*.lua'):
            loaded = loadfile(str(file))
            self.assertFalse(isinstance(loaded, tuple), f'{file}: {loaded}')
        obj = self.lua.table_from({'path': 'C:\\照片\\a"\n.NEF', 'value': 0.3})
        self.assertEqual(json.loads(self.common.json(obj))['path'], 'C:\\照片\\a"\n.NEF')

    def run_apply(self, mutate=None, fail_second=False):
        plan, _, _ = self.plan()
        if fail_second:
            d = copy.deepcopy(self.decisions)
            d['photos'].append({'photo_id': '124', 'path': self.manifest['photos'][1]['path'],
                'reason': '略暗', 'subject': 'landscape', 'confidence': 'high', 'status': 'ready', 'settings': {'Exposure2012': 0.2}})
            plan = self.plan(d)[0]
        with tempfile.TemporaryDirectory(dir=None) as tmp:
            path = Path(tmp) / 'plan.tsv'
            path.write_text(plan, encoding='utf-8')
            self.lua.globals().plugin_path = PLUGIN.as_posix()
            self.lua.globals().plan_path = str(path)
            self.lua.globals().catalog_path = self.manifest['catalog']
            self.lua.globals().photo_path = self.manifest['photos'][0]['path']
            self.lua.globals().second_path = self.manifest['photos'][1]['path']
            self.lua.execute('''
                calls=0; snapshots=0; messages={}
                current={Exposure2012=0.6, Highlights2012=0, Vibrance=0, Sharpness=40, SharpenRadius=1,
                    SharpenDetail=25, SharpenEdgeMasking=0, Clarity2012=0, Dehaze=0}
                p={localIdentifier=123}
                function p:getRawMetadata(k) if k=='path' then return photo_path else return 'RAW' end end
                function p:getDevelopSettings() return current end
                function p:createDevelopSnapshot(name,replace) assert(not replace); snapshots=snapshots+1 end
                function p:applyDevelopSettings(s) calls=calls+1; for k,v in pairs(s) do current[k]=v end end
                p2={localIdentifier=124}
                function p2:getRawMetadata(k) if k=='path' then return second_path else return 'RAW' end end
                function p2:getDevelopSettings() return {Exposure2012=0, Highlights2012=0, Vibrance=0, Clarity2012=0, Dehaze=0} end
                function p2:createDevelopSnapshot() snapshots=snapshots+1 end
                function p2:applyDevelopSettings() error('Simulated Adobe error') end
                catalog={}
                function catalog:getPath() return catalog_path end
                function catalog:getTargetPhotos() return {p,p2} end
                function catalog:withWriteAccessDo(name,fn,opts) fn() end
                _PLUGIN={path=plugin_path}
                modules={
                    LrApplication={activeCatalog=function() return catalog end},
                    LrTasks={startAsyncTask=function(fn) fn() end,pcall=pcall},
                    LrPathUtils={child=function(a,b) return a..'/'..b end},
                    LrDialogs={runOpenPanel=function() return {plan_path} end,
                        message=function(title,body) messages[#messages+1]={title=title,body=body} end}
                }
                function import(name) return modules[name] end
            ''')
            if mutate:
                self.lua.execute(mutate)
            self.lua.execute((PLUGIN / 'Apply.lua').read_text(encoding='utf-8'))
            return self.lua.globals().calls, self.lua.globals().snapshots, self.lua.globals().messages

    def test_apply_success_and_stale_abort(self):
        calls, snapshots, _ = self.run_apply()
        self.assertEqual((calls, snapshots), (1, 0))
        for mutation in ['current.Exposure2012=0.7', 'current.Sharpness=80', "catalog_path='other'", "photo_path='wrong'",
                         'function catalog:getTargetPhotos() return {} end']:
            calls, snapshots, msgs = self.run_apply(mutation)
            self.assertEqual((calls, snapshots), (0, 0))
            self.assertEqual(msgs[1]['title'], 'Local apply stopped')

    def test_partial_failure_stops(self):
        calls, snapshots, msgs = self.run_apply(fail_second=True)
        self.assertEqual((calls, snapshots), (1, 0))
        self.assertIn('Completed calls: 1', msgs[1]['body'])

    def test_all_batch_validation_before_first_mutation(self):
        calls, snapshots, _ = self.run_apply(
            'function p2:getDevelopSettings() return {Exposure2012=1} end', fail_second=True)
        self.assertEqual((calls, snapshots), (0, 0))

    def test_export_manifest_and_binary_preview(self):
        with tempfile.TemporaryDirectory(dir=None) as tmp:
            g = self.lua.globals()
            g.plugin_path = PLUGIN.as_posix()
            g.output_path = Path(tmp).as_posix()
            g.catalog_path = self.manifest['catalog']
            g.photo_path = self.manifest['photos'][0]['path']
            g.py_exists = lambda p: Path(p).exists()
            g.py_mkdir = lambda p: Path(p).mkdir(parents=True, exist_ok=True)
            g.py_jpeg = lambda p: Path(p).write_bytes(b'\xff\xd8binary\n\r\xff\xd9')
            self.lua.execute('''
                messages={}
                p={localIdentifier=123}
                function p:getRawMetadata(k)
                    if k=='path' then return photo_path end
                    if k=='fileFormat' then return 'RAW' end
                    if k=='isoSpeedRating' then return 100 end
                end
                function p:getDevelopSettings() return {Exposure2012=0.6, Highlights2012=0} end
                function p:requestJpegThumbnail(w,h,fn)
                    assert(w==1600 and h==1600)
                    fn(string.char(255,216)..'binary\\n\\r'..string.char(255,217))
                    return {}
                end
                catalog={}
                function catalog:getPath() return catalog_path end
                function catalog:getTargetPhotos() return {p} end
                _PLUGIN={path=plugin_path}
                modules={
                    LrExportSession=function(opts)
                        local s=opts.exportSettings
                        assert(s.LR_format=='JPEG' and s.LR_export_colorSpace=='sRGB')
                        assert(s.LR_reimportExportedPhoto==false and s.LR_outputSharpeningOn==false)
                        assert(s.LR_size_maxWidth==1024 and s.LR_size_maxHeight==1024)
                        local rendition={photo=opts.photosToExport[1]}
                        function rendition:waitForRender()
                            local path=s.LR_export_destinationPathPrefix..'/test.jpg'
                            py_jpeg(path);return true,path
                        end
                        return {renditions=function()
                            local done=false
                            return function() if done then return nil end;done=true;return 1,rendition end
                        end}
                    end,
                    LrApplication={activeCatalog=function() return catalog end},
                    LrTasks={startAsyncTask=function(fn) fn() end,pcall=pcall,sleep=function() end},
                    LrPathUtils={child=function(a,b) return a..'/'..b end},
                    LrFileUtils={exists=py_exists,createAllDirectories=py_mkdir},
                    LrDialogs={runOpenPanel=function() return {output_path} end,
                        message=function(title,body) messages[#messages+1]={title=title,body=body} end}
                }
                function import(name) return modules[name] end
            ''')
            self.lua.execute((PLUGIN / 'Export.lua').read_text(encoding='utf-8'))
            manifest_file = next(Path(tmp).glob('*/manifest.json'))
            manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
            self.assertEqual(manifest['photos'][0]['photo_id'], '123')
            self.assertEqual(manifest['catalog'], self.manifest['catalog'])
            self.assertEqual(manifest['failures'], [])
            preview = manifest_file.parent / manifest['photos'][0]['preview']
            self.assertEqual(preview.read_bytes(), b'\xff\xd8binary\n\r\xff\xd9')

    def test_portrait_no_sharpening_landscape_preserved(self):
        d = copy.deepcopy(self.decisions)
        d['photos'][0]['subject'] = 'portrait'
        d['photos'][0]['settings'] = {'Sharpness': 80}
        plan, presets, report = self.plan(d)
        self.assertIn('Sharpness\t0\t40', plan)
        self.assertEqual(report['ready'][0]['settings']['Sharpness'], 0)
        d['photos'][0]['subject'] = 'landscape'
        for key, val in [('Sharpness', 80), ('SharpenRadius', 2), ('SharpenDetail', 50), ('SharpenEdgeMasking', 30)]:
            d['photos'][0]['settings'] = {key: val}
            with self.assertRaises(ValueError):
                self.plan(d)
        plan, presets, _ = self.plan()
        desc = ET.fromstring(presets['123']).find(f'.//{{{bp.RDF}}}Description')
        for key in bp.SHARPENING:
            self.assertNotIn(f'{{{bp.CRS}}}{key}', desc.attrib)
        self.assertEqual(report['ready'][0]['policy_settings'], {'Sharpness':0})
        _,_,landscape_report=self.plan()
        self.assertEqual(landscape_report['ready'][0]['policy_settings'],{'Clarity2012':20,'Dehaze':20})
        self.assertNotIn('Clarity2012',landscape_report['ready'][0]['model_settings'])

    def test_auto_tone_is_not_skipped_when_model_gives_zero(self):
        d=copy.deepcopy(self.decisions)
        d['photos'][0]['settings']={}
        d['photos'][0]['auto_tone']=True
        for key in bp.TONE:
            self.manifest['photos'][0]['settings'].setdefault(key,0)
        plan,_,report=self.plan(d)
        self.assertEqual(len(report['ready']),1)
        self.assertIn('Action_AutoTone\t1\t1',plan)
        with tempfile.TemporaryDirectory(dir=None) as tmp:
            p=Path(tmp)/'auto.tsv';p.write_text(plan,encoding='utf-8')
            _,items,_=self.common.readPlan(str(p))
            self.assertTrue(items['123']['autoTone'])
            self.assertEqual(items['123']['baseline']['Sharpness'],40)

    def test_auto_colour_preserved_portrait_vibrance_conservative(self):
        d=copy.deepcopy(self.decisions)
        d['photos'][0]['subject']='other'
        d['photos'][0]['settings']={'Vibrance':30}
        _,_,report=self.plan(d)
        self.assertEqual(report['ready'],[])
        self.manifest['photos'][0]['settings']['Vibrance']=11
        _,_,report=self.plan(d)
        self.assertEqual(report['ready'],[])
        d['photos'][0]['subject']='portrait'
        _,_,report=self.plan(d)
        self.assertEqual(report['ready'][0]['settings']['Vibrance'],8)
        self.assertEqual(report['ready'][0]['settings']['Sharpness'],0)
        d['photos'][0]['subject']='other'
        self.manifest['photos'][0]['settings']['Vibrance']=0
        _,_,report=self.plan(d)
        self.assertEqual(report['ready'],[])
        d['photos'][0]['subject']='portrait'
        self.manifest['photos'][0]['settings']['Vibrance']=-8
        _,_,report=self.plan(d)
        self.assertNotIn('Vibrance',report['ready'][0]['settings'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
