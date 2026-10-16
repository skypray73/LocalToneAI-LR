"""Recover an interrupted analysis by retrying only failed photos; never change Lightroom."""
import argparse
import json
from pathlib import Path
from analyze_local import api, analyze_photo, write_json
from build_plan import compile_plan


def recover(batch, out):
    batch, out = Path(batch).resolve(), Path(out).resolve()
    if (batch / 'local-result.tsv').exists():
        raise ValueError('Completion marker exists; refusing possible repeated application')
    if not out.is_relative_to(batch) or out.exists():
        raise ValueError('Output must be a new folder inside the batch')
    previous = batch / 'local-result'
    manifest = json.loads((batch / 'manifest.json').read_text(encoding='utf-8-sig'))
    decisions = json.loads((previous / 'decisions.json').read_text(encoding='utf-8'))
    failures = json.loads((previous / 'failures.json').read_text(encoding='utf-8'))
    compile_plan(manifest, decisions)
    photos = {str(p['photo_id']): p for p in manifest['photos']}
    good = [str(p['photo_id']) for p in decisions['photos']]
    failed = [str(p['photo_id']) for p in failures]
    if (len(photos) != len(manifest['photos']) or len(set(good + failed)) != len(good + failed)
            or set(good + failed) != set(photos)):
        raise ValueError('Previous results must cover every manifest identity exactly once')
    model = decisions['model']
    if 'cloud' in model.lower() or not any(m.get('name') == model and not m.get('remote_host')
            for m in api('/api/tags', timeout=10).get('models', [])):
        raise ValueError('Require the previously used model downloaded locally')
    out.mkdir()
    remaining = []
    for pid in failed:
        photo = dict(photos[pid], pipeline_stage=photos[pid].get('pipeline_stage', manifest.get('pipeline_stage', 'current-develop')))
        try:
            preview = (batch / photo['preview']).resolve()
            if not preview.is_relative_to(batch):
                raise ValueError('Preview must stay inside the batch folder')
            decision, raw = analyze_photo(photo, preview, model, decisions['style'])
            decision['auto_tone'] = False
            compile_plan(manifest, {'photos': [decision]})
            decisions['photos'].append(decision)
            write_json(out / ('analysis-' + pid + '.json'), raw)
            print('Recovered ID ' + pid, flush=True)
        except Exception as exc:
            remaining.append({'photo_id': pid, 'error': str(exc)})
        write_json(out / 'decisions.json', decisions)
        write_json(out / 'failures.json', remaining)
    plan, _, report = compile_plan(manifest, decisions)
    (out / 'plan.tsv').write_text(plan, encoding='utf-8', newline='\n')
    report.update(source='local-ollama', model=model, failures=remaining,
                  recovery={'previous_result': str(previous), 'retried': len(failed)})
    write_json(out / 'report.json', report)
    print(f'Plan only: {len(report["ready"])} ready, {len(report["skipped"])} skipped, '
          f'{len(remaining)} failed. Lightroom application pending.', flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    recover(args.batch, args.out)
