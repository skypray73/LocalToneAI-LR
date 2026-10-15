"""Start local Ollama, analyse an exported batch, and signal Lightroom to apply it."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from analyze_local import api


def run_job(job_file):
    job = json.loads(Path(job_file).read_text(encoding='utf-8-sig'))
    batch = Path(job['batch']).resolve()
    result = batch / 'local-result'
    marker = batch / 'local-result.tsv'
    if marker.exists() or result.exists():
        raise ValueError('Job already processed; refusing to repeat or overwrite')
    env = os.environ.copy()
    env.update(OLLAMA_MODELS=r'C:\AI\Models\Ollama', OLLAMA_NO_CLOUD='1',
               OLLAMA_HOST='127.0.0.1:11434', OLLAMA_CONTEXT_LENGTH='8192', OLLAMA_NUM_PARALLEL='1')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        api('/api/version', timeout=2)
    except OSError:
        with (batch / 'ollama-start.log').open('ab') as log:
            subprocess.Popen([r'C:\AI\Ollama\ollama.exe', 'serve'], env=env,
                stdout=log, stderr=log, creationflags=flags)
        for _ in range(60):
            time.sleep(0.5)
            try:
                api('/api/version', timeout=1)
                break
            except OSError:
                pass
        else:
            raise RuntimeError('Local Ollama did not start; see ollama-start.log')
    with (batch / 'analysis.log').open('wb') as log:
        completed = subprocess.run([sys.executable, str(Path(__file__).with_name('analyze_local.py')),
            '--manifest', str(batch / 'manifest.json'), '--out', str(result)], env=env,
            stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    if completed.returncode not in (0, 1) or not (result / 'report.json').exists():
        raise RuntimeError('Model refinement failed; see analysis.log. No model refinement applied.')
    report = json.loads((result / 'report.json').read_text(encoding='utf-8'))
    if report.get('failures'):
        raise RuntimeError('Some photos failed analysis. Automatic apply stopped; see local-result/report.json.')
    skipped_unchanged = sum(p['reason'].startswith('No change needed:') for p in report['skipped'])
    review = len(report['skipped']) - skipped_unchanged
    model_jobs = sum(bool(p['model_settings']) for p in report['ready'])
    policy_jobs = sum(bool(p['policy_settings']) for p in report['ready'])
    unchanged = skipped_unchanged + sum(not p['model_settings'] for p in report['ready'])
    marker.write_text('LRRESULT\t3\t' + '\t'.join(map(str,
        [len(report['ready']), model_jobs, policy_jobs, unchanged, review, 0])) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job', required=True)
    args = p.parse_args()
    try:
        sys.exit(run_job(args.job))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
