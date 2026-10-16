import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyze_local
import resume_failed
from run_lightroom_job import completion_marker


class PartialTests(unittest.TestCase):
    def test_mixed_batch_keeps_per_photo_stage_for_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            photos = [{'photo_id': str(i), 'path': f'D:/Photos/{i}.NEF', 'preview': f'{i}.jpg',
                       'file_format': 'RAW', 'settings': {'Exposure2012': 0}, 'pipeline_stage': stage}
                      for i, stage in enumerate(['current-develop', 'after-lightroom-auto'], 1)]
            manifest = {'version': 1, 'catalog': 'test.lrcat',
                        'pipeline_stage': 'mixed-auto-and-current-develop', 'photos': photos}
            path = root/'manifest.json'
            path.write_text(json.dumps(manifest))
            def analyze(photo, *args):
                return {'photo_id': photo['photo_id'], 'path': photo['path'], 'subject': 'other',
                        'confidence': 'high', 'status': 'ready', 'reason': 'Test',
                        'settings': {'Exposure2012': .2}}, {}
            with patch.object(sys, 'argv', ['analyze_local.py', '--manifest', str(path), '--out', str(root/'out')]), \
                    patch.object(analyze_local, 'api', return_value={'models': [{'name': 'qwen3-vl:8b-instruct'}]}), \
                    patch.object(analyze_local, 'analyze_photo', side_effect=analyze) as call:
                analyze_local.main()
                self.assertEqual([c.args[0]['pipeline_stage'] for c in call.call_args_list],
                                 ['current-develop', 'after-lightroom-auto'])
            decisions = json.loads((root/'out/decisions.json').read_text(encoding='utf-8'))
            self.assertTrue(all(p['auto_tone'] is False for p in decisions['photos']))

    def test_incomplete_reply_retried_once_with_larger_budget(self):
        valid = {'done': True, 'message': {'content': '{"subject":"portrait"}'}}
        with patch.object(analyze_local, 'api', side_effect=[{'done': False}, valid]) as api:
            self.assertEqual(analyze_local.request_result({'options': {}})['subject'], 'portrait')
            self.assertEqual([c.args[1]['options']['num_predict'] for c in api.call_args_list], [768, 1536])
        with patch.object(analyze_local, 'api', return_value={'done': False}) as api:
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                analyze_local.request_result({'options': {}})
            self.assertEqual(api.call_count, 2)

    def test_partial_marker_keeps_failure_separate(self):
        report = {'ready': [{'model_settings': {'Exposure2012': .2}, 'policy_settings': {}}],
                  'skipped': [{'reason': 'No change needed: stable'}, {'reason': 'Low confidence'}],
                  'failures': [{'photo_id': '3'}]}
        self.assertEqual(completion_marker(report), 'LRRESULT\t4\t1\t1\t0\t1\t1\t1\n')

    def test_recovery_retains_good_results_and_refuses_unsafe_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / 'local-result'
            old.mkdir()
            manifest = {'version': 1, 'catalog': 'test.lrcat', 'photos': [
                {'photo_id': pid, 'path': 'D:/Photos/' + pid + '.NEF', 'preview': pid + '.jpg',
                 'file_format': 'RAW', 'settings': {'Exposure2012': 0}} for pid in ['1', '2']]}
            def decision(pid):
                return {'photo_id': pid, 'path': 'D:/Photos/' + pid + '.NEF', 'subject': 'other',
                        'confidence': 'high', 'status': 'ready', 'reason': 'Test correction',
                        'settings': {'Exposure2012': .2}, 'auto_tone': False}
            decisions = {'model': 'test-local', 'style': 'natural', 'photos': [decision('1')]}
            for path, value in [(root/'manifest.json', manifest), (old/'decisions.json', decisions),
                                (old/'failures.json', [{'photo_id': '2', 'error': 'incomplete'}])]:
                path.write_text(json.dumps(value), encoding='utf-8')
            original = {p: p.read_bytes() for p in old.iterdir()}
            with patch.object(resume_failed, 'api', return_value={'models': [{'name': 'test-local'}]}), \
                    patch.object(resume_failed, 'analyze_photo', return_value=(decision('2'), {})) as analyze:
                report = resume_failed.recover(root, root/'recovered')
                self.assertEqual(analyze.call_count, 1)
                self.assertEqual(analyze.call_args.args[0]['photo_id'], '2')
                self.assertEqual(len(report['ready']), 2)
                recovered = json.loads((root/'recovered/decisions.json').read_text())
                self.assertEqual(recovered['photos'][0], decisions['photos'][0])
                self.assertEqual({p: p.read_bytes() for p in old.iterdir()}, original)
                (old/'failures.json').write_text('[{"photo_id":"unknown"}]')
                with self.assertRaisesRegex(ValueError, 'identity'):
                    resume_failed.recover(root, root/'bad')
                (root/'local-result.tsv').write_text('already processed')
                with self.assertRaisesRegex(ValueError, 'Completion marker'):
                    resume_failed.recover(root, root/'repeat')


if __name__ == '__main__':
    unittest.main()
