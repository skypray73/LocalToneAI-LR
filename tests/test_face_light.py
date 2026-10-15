from pathlib import Path
import base64
import io
import sys
import unittest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import face_light as face
import analyze_local as local


class FaceTests(unittest.TestCase):
    def fixture(self, brightness=55):
        image = Image.new('RGB', (400, 400), (230, 230, 230))
        ImageDraw.Draw(image).rectangle((140, 80, 239, 219), fill=(brightness,)*3)
        row = [140, 80, 100, 140]+[165,129,215,129,190,157,175,189,205,189]+[.95]
        metrics = face.measure_faces(image, [row])
        return image, metrics

    def test_local_measurements_exclude_bright_background(self):
        image, m = self.fixture()
        self.assertEqual(m['dark_face_count'], 1)
        self.assertEqual(m['faces'][0]['luma_p65'], 55)
        self.assertEqual(m['faces'][0]['background_minus_face'], 175)
        crop = Image.open(io.BytesIO(base64.b64decode(face.face_sheet(image, m))))
        self.assertEqual(crop.size, (256, 256))

    def test_tiny_faces_and_bystanders_not_measurement_targets(self):
        image, m = self.fixture()
        rows = [[140, 80, 100, 140]+[0]*10+[.95],
                [0, 0, 20, 20]+[0]*10+[.99], [300, 300, 30, 30]+[0]*10+[.95]]
        self.assertEqual(len(face.measure_faces(image, rows)['faces']), 1)

    def test_dark_glasses_do_not_make_well_lit_skin_dark(self):
        image,_ = self.fixture(150)
        # Eye/lens band: visible forehead and cheeks stay bright.
        ImageDraw.Draw(image).rectangle((145,117,234,151), fill='black')
        row = [140,80,100,140,165,129,215,129,190,157,175,189,205,189,.95]
        f = face.measure_faces(image,[row])['faces'][0]
        self.assertFalse(f['dark_evidence'])
        self.assertGreaterEqual(f['skin_samples']['reliable_regions'],2)
        self.assertEqual(f['luma_p65'],150)

    def test_dark_forehead_alone_does_not_trigger_fill(self):
        image,_ = self.fixture(150)
        ImageDraw.Draw(image).rectangle((150,85,229,112),fill=(45,45,45))
        row = [140,80,100,140,165,129,215,129,190,157,175,189,205,189,.95]
        f=face.measure_faces(image,[row])['faces'][0]
        self.assertFalse(f['dark_evidence'])
        self.assertEqual(f['skin_samples']['dark_regions'],1)

    def decision(self, lighting, subject='portrait', brightness=55, highlights=250):
        _, m = self.fixture(brightness)
        photo = {'photo_id':'1', 'path':'X:/a.NEF',
                 'settings':{'Shadows2012':31, 'Highlights2012':-45, 'Exposure2012':-.8}}
        result = {'subject':subject, 'face_lighting':lighting, 'confidence':'high',
                  'needs_review':False, 'reason':'臉部光線',
                  'deltas':{'Shadows2012':0, 'Exposure2012':.2, 'Highlights2012':0}}
        return local.convert_result(photo, result,
            {'face_analysis':m, 'rendered_luma_p99':highlights})

    def test_ai_and_measurement_agree_lift_shadows_despite_bright_sky(self):
        d = self.decision('underexposed')
        self.assertEqual(d['settings']['Shadows2012'], 71)
        self.assertEqual(d['settings']['Highlights2012'], -60)
        self.assertNotIn('Exposure2012', d['settings'])
        self.assertEqual(d['status'], 'ready')
        self.assertEqual(d['face_assist']['added_deltas']['Shadows2012'], 40)

    def test_natural_dark_skin_or_silhouette_not_automatically_brightened(self):
        d = self.decision('intentional')
        self.assertNotIn('Shadows2012', d['settings'])
        d = self.decision('adequate')
        self.assertEqual(d['status'], 'ready')
        self.assertEqual(d['settings']['Shadows2012'], 46)
        self.assertEqual(d['face_assist']['basis'], 'measured_skin_fill_preference')

    def test_skin_fill_keeps_bright_sky_from_global_exposure_lift(self):
        d=self.decision('underexposed',highlights=242)
        self.assertNotIn('Exposure2012',d['settings'])
        self.assertIn('Exposure2012',d['highlight_protection'])
        self.assertGreater(d['settings']['Shadows2012'],31)

    def test_well_lit_faces_and_landscapes_no_forced_floor(self):
        d = self.decision('adequate', brightness=150)
        self.assertEqual(d['status'], 'ready')
        self.assertNotIn('Shadows2012', d['settings'])

    def test_mixed_faces_near_clipping_require_local_edit(self):
        _, m = self.fixture()
        bright = dict(m['faces'][0], luma_p90=250, dark_evidence=False)
        m['faces'].append(bright)
        assist = face.face_adjustments({'subject':'portrait','face_lighting':'underexposed','deltas':{}},
                                      {'face_analysis':m})
        self.assertTrue(assist['review_reason'])
        self.assertEqual(assist['added_deltas'], {})
        d = self.decision('not_applicable', subject='landscape')
        self.assertEqual(d['status'], 'ready')
        self.assertNotIn('Shadows2012', d['settings'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
