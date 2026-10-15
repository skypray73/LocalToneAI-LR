from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import analyze_local as local
from build_plan import compile_plan
from PIL import Image


class LocalTests(unittest.TestCase):
    def test_night_shadows_wider_than_day_without_changing_other_limits(self):
        self.photo['settings']['Shadows2012']=5
        self.result['deltas']={'Shadows2012':90}
        self.result['scene_lighting']='night'
        d=local.convert_result(self.photo,self.result,{})
        self.assertEqual(d['settings']['Shadows2012'],95)
        self.assertEqual(d['status'],'ready')
        self.result['scene_lighting']='day_or_indoor'
        d=local.convert_result(self.photo,self.result,{})
        self.assertEqual(d['settings']['Shadows2012'],75)
        self.assertEqual(d['status'],'needs_review')
        self.result['scene_lighting']='night'
        self.result['deltas']={'Shadows2012':100,'Exposure2012':.3}
        d=local.convert_result(self.photo,self.result,{'rendered_luma_p99':250})
        self.assertEqual(d['settings']['Shadows2012'],100)
        self.assertNotIn('Exposure2012',d['settings'])
        self.assertEqual(d['status'],'ready')

    def setUp(self):
        self.photo = {'photo_id': '12', 'path': 'C:\\照片\\private.NEF', 'file_format': 'RAW',
            'settings': {'Exposure2012': 0.6, 'Highlights2012': -10, 'Vibrance': 0, 'Sharpness': 40,
                         'SharpenRadius': 1, 'SharpenDetail': 25, 'SharpenEdgeMasking': 0}}
        self.result = {'subject': 'portrait', 'confidence': 'high', 'needs_review': False,
                       'reason': '人像稍暗', 'deltas': {'Exposure2012': 0.2}}

    def test_delta_conversion_and_portrait_policy(self):
        decision = local.convert_result(self.photo, self.result, {})
        self.assertEqual(decision['settings']['Exposure2012'], 0.8)
        _, _, report = compile_plan({'version': 1, 'catalog': 'cat', 'photos': [self.photo]}, {'photos': [decision]})
        self.assertEqual(report['ready'][0]['settings']['Sharpness'], 0)

    def test_limits_missing_baseline_and_review(self):
        self.result['deltas'] = {'Exposure2012': 20, 'Saturation': 5}
        decision = local.convert_result(self.photo, self.result, {})
        self.assertEqual(decision['settings']['Exposure2012'], 1.1)
        self.assertEqual(decision['status'], 'needs_review')
        self.assertNotIn('Saturation', decision['settings'])
        for bad in [True, float('nan'), '0.2']:
            self.result['deltas'] = {'Exposure2012': bad}
            with self.assertRaises(ValueError):
                local.convert_result(self.photo, self.result, {})
        self.result['deltas'] = {'Sharpness': 100}
        with self.assertRaises(ValueError):
            local.convert_result(self.photo, self.result, {})

    def test_statistics_and_no_identifiers_in_model_request(self):
        with tempfile.TemporaryDirectory(dir=None) as tmp:
            image = Path(tmp) / 'fixture.jpg'
            from PIL import ImageDraw
            picture=Image.new('RGB', (64, 64), 'white')
            ImageDraw.Draw(picture).rectangle((0,0,31,63),fill='black')
            picture.save(image)
            encoded, stats = local.preview_data(image)
            self.assertGreater(stats['near_white_fraction'], 0.4)
            self.assertLess(stats['near_white_fraction'], 0.6)
            original_api = local.api
            captured = {}
            def fake_api(route, payload):
                captured.update(payload)
                import json
                return {'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps(self.result)}}
            local.api = fake_api
            try:
                local.analyze_photo(self.photo, image, 'qwen3-vl:8b', '自然')
            finally:
                local.api = original_api
            import json
            self.assertNotIn(self.photo['path'], json.dumps(captured, ensure_ascii=False))
            self.assertEqual(captured['messages'][1]['images'], [encoded])

    def test_blank_preview_rejected_before_model(self):
        with tempfile.TemporaryDirectory(dir=None) as tmp:
            path=Path(tmp)/'blank.jpg'
            Image.new('RGB',(64,64),'white').save(path)
            with self.assertRaisesRegex(ValueError,'空白'):
                local.preview_data(path)

    def test_highlight_protection_and_larger_shadow_range(self):
        self.photo['settings'].update(Whites2012=0,Shadows2012=10)
        self.result['deltas']={'Exposure2012':0.3,'Highlights2012':25,'Whites2012':15,'Shadows2012':40}
        decision=local.convert_result(self.photo,self.result,{'rendered_luma_p99':250,'near_white_fraction':0.01})
        self.assertNotIn('Exposure2012',decision['settings'])
        self.assertNotIn('Highlights2012',decision['settings'])
        self.assertNotIn('Whites2012',decision['settings'])
        self.assertEqual(decision['settings']['Shadows2012'],50)
        self.assertEqual(len(decision['highlight_protection']),3)
        self.assertEqual(decision['status'],'ready')

    def test_face_shadow_range_70_with_highlight_protection(self):
        self.photo['settings'].update(Shadows2012=20,Whites2012=0)
        self.result['deltas']={'Shadows2012':70,'Highlights2012':-60,'Exposure2012':0.3}
        d=local.convert_result(self.photo,self.result,{'rendered_luma_p99':250})
        self.assertEqual(d['settings']['Shadows2012'],90)
        self.assertEqual(d['settings']['Highlights2012'],-70)
        self.assertNotIn('Exposure2012',d['settings'])
        self.assertEqual(d['status'],'ready')
        self.photo['settings']['Shadows2012']=70
        d=local.convert_result(self.photo,self.result,{'rendered_luma_p99':250})
        self.assertEqual(d['settings']['Shadows2012'],100)
        self.assertIn(70,local.STEPS['Shadows2012'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
