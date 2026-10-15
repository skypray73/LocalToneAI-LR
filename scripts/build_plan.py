"""Compile reviewed visual decisions into a data-only Lightroom plan and XMP presets."""
import argparse
import json
import math
from pathlib import Path
from urllib.parse import quote
import uuid
import xml.etree.ElementTree as ET

RANGES = {
    'Exposure2012': (-5, 5),
    **{k: (-100, 100) for k in ('Contrast2012', 'Highlights2012', 'Shadows2012',
        'Whites2012', 'Blacks2012', 'Texture', 'Clarity2012', 'Dehaze', 'Vibrance',
        'Saturation', 'RelativeTemperature', 'RelativeTint')},
    'Temperature': (2000, 50000), 'Tint': (-150, 150), 'Sharpness': (0, 150),
    'SharpenRadius': (0.5, 3),
    **{k: (0, 100) for k in ('SharpenDetail', 'SharpenEdgeMasking',
        'LuminanceSmoothing', 'ColorNoiseReduction')},
}
CRS = 'http://ns.adobe.com/camera-raw-settings/1.0/'
SHARPENING = {'Sharpness', 'SharpenRadius', 'SharpenDetail', 'SharpenEdgeMasking'}
TONE = {'Exposure2012', 'Contrast2012', 'Highlights2012', 'Shadows2012', 'Whites2012', 'Blacks2012'}
RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
ET.register_namespace('x', 'adobe:ns:meta/')
ET.register_namespace('rdf', RDF)
ET.register_namespace('crs', CRS)


def scalar(value):
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'Invalid scalar: {value!r}')
    return format(value, '.15g')


def xmp(name, settings):
    root = ET.Element('{adobe:ns:meta/}xmpmeta')
    rdf = ET.SubElement(root, f'{{{RDF}}}RDF')
    d = ET.SubElement(rdf, f'{{{RDF}}}Description', {f'{{{RDF}}}about': ''})
    attrs = {'PresetType': 'Normal', 'UUID': uuid.uuid4().hex.upper(),
             'SupportsAmount': 'False', 'SupportsColor': 'True',
             'SupportsMonochrome': 'True', 'SupportsHighDynamicRange': 'True',
             'SupportsNormalDynamicRange': 'True', 'SupportsSceneReferred': 'True',
             'SupportsOutputReferred': 'True', 'HasSettings': 'True'}
    for key, val in {**attrs, **settings}.items():
        d.set(f'{{{CRS}}}{key}', scalar(val))
    for key, val in [('Name', name), ('Group', '本地 AI 顯影')]:
        alt = ET.SubElement(ET.SubElement(d, f'{{{CRS}}}{key}'), f'{{{RDF}}}Alt')
        ET.SubElement(alt, f'{{{RDF}}}li', {'{http://www.w3.org/XML/1998/namespace}lang': 'x-default'}).text = val
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def compile_plan(manifest, decisions, include_review=False):
    if manifest.get('version') != 1 or not manifest.get('catalog'):
        raise ValueError('Require a version 1 plugin manifest with catalog')
    photos = {}
    for p in manifest['photos']:
        pid = str(p['photo_id'])
        if not pid.isdigit() or pid in photos:
            raise ValueError('Duplicate or invalid manifest photo_id')
        photos[pid] = p
    rows = ['LRPLAN\t1\t' + quote(manifest['catalog'], safe='')]
    report = {'style': decisions.get('style', '自然'), 'ready': [], 'skipped': [],
              'unanalysed': [], 'lightroom_applied': False, 'visual_verified': False}
    seen, presets = set(), {}
    for d in decisions['photos']:
        pid = str(d['photo_id'])
        if pid in seen or pid not in photos:
            raise ValueError(f'Duplicate or unknown photo ID: {pid}')
        seen.add(pid)
        p = photos[pid]
        if d.get('path') != p['path']:
            raise ValueError(f'Path mismatch: {pid}')
        if d.get('confidence') not in ('high', 'medium', 'low') or d.get('status') not in ('ready', 'needs_review'):
            raise ValueError(f'Invalid confidence/status: {pid}')
        if not isinstance(d.get('reason'), str) or not d['reason'].strip():
            raise ValueError(f'Missing visual reasoning: {pid}')
        if not include_review and (d['confidence'] == 'low' or d['status'] == 'needs_review'):
            report['skipped'].append({'photo_id': pid, 'reason': d['reason'],
                                      'face_assist': d.get('face_assist'), 'metrics': d.get('metrics')})
            continue
        if not isinstance(d['settings'], dict):
            raise ValueError(f'settings must be an object: {pid}')
        settings = dict(d['settings'])
        subject = d.get('subject')
        if subject not in ('portrait', 'landscape', 'other'):
            raise ValueError(f'Classify subject as portrait/landscape/other: {pid}')
        raw = p.get('file_format') in ('RAW', 'DNG')
        baseline = p['settings']
        auto_tone = d.get('auto_tone', False)
        if not isinstance(auto_tone, bool):
            raise ValueError('auto_tone must be boolean')
        if auto_tone:
            if TONE & settings.keys():
                raise ValueError('Cannot mix automatic tone with absolute tone targets')
            for key in TONE:
                if key not in baseline:
                    raise ValueError(f'Missing auto tone baseline: {pid}/{key}')
                scalar(baseline[key])
        # Colour follows Lightroom Auto; model deltas must not replace its colour decisions.
        settings.pop('Vibrance', None)
        settings.pop('Saturation', None)
        if subject == 'portrait':
            settings['Sharpness'] = 0
            original = baseline.get('Vibrance')
            scalar(original)
            if isinstance(original, bool) or not isinstance(original, (int, float)):
                raise ValueError(f'Missing numeric vibrance baseline: {pid}')
            if original > 0:
                settings['Vibrance'] = int(math.floor(original * 0.7 + 0.5))
        elif subject == 'landscape':
            settings['Clarity2012'] = 20
            settings['Dehaze'] = 20
        policy_keys = ({'Vibrance','Sharpness'} if subject == 'portrait' else
                       {'Clarity2012','Dehaze'} if subject == 'landscape' else set())
        preserve = SHARPENING - {'Sharpness'} if subject == 'portrait' else SHARPENING
        for key in preserve & settings.keys():
            if settings[key] != baseline.get(key):
                raise ValueError(f'Preserve exported sharpening for {subject}: {pid}/{key}')
        wb = any(k in settings for k in ('Temperature', 'Tint', 'RelativeTemperature', 'RelativeTint'))
        if wb and settings.get('WhiteBalance') != 'Custom':
            raise ValueError(f'White balance values require WhiteBalance=Custom: {pid}')
        changed = {}
        for key, value in sorted(settings.items()):
            if key == 'WhiteBalance':
                if value != 'Custom' or not wb:
                    raise ValueError(f'WhiteBalance only supported alongside numeric WB: {pid}')
                if not isinstance(baseline.get(key), str):
                    raise ValueError(f'Missing WB baseline: {pid}')
            else:
                if key not in RANGES:
                    raise ValueError(f'Unsupported setting: {key}')
                scalar(value)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError(f'Numeric setting required: {key}')
                lo, hi = RANGES[key]
                if not lo <= value <= hi:
                    raise ValueError(f'Out of range: {key}={value}')
                if (key in ('Temperature', 'Tint') and not raw) or (key in ('RelativeTemperature', 'RelativeTint') and raw):
                    raise ValueError(f'Wrong WB units for {p.get("file_format")}: {key}')
                if key not in baseline or isinstance(baseline[key], (str, bool)):
                    raise ValueError(f'Missing numeric baseline: {pid}/{key}')
                scalar(baseline[key])
            if value != baseline[key]:
                changed[key] = value
        # Keep WhiteBalance=Custom with numeric WB even if mode is already Custom.
        if wb and any(k in changed for k in ('Temperature', 'Tint', 'RelativeTemperature', 'RelativeTint')):
            changed['WhiteBalance'] = 'Custom'
        if not changed and not auto_tone:
            report['skipped'].append({'photo_id': pid, 'reason': 'No change needed: ' + d['reason'],
                                      'face_assist': d.get('face_assist'), 'metrics': d.get('metrics')})
            continue
        guards = set(RANGES) & baseline.keys() if auto_tone else SHARPENING & baseline.keys() if subject != 'portrait' else set()
        if guards:
            for key in sorted(guards):
                val = scalar(baseline[key])
                rows.append('\t'.join([pid, quote(p['path'], safe=''), 'Guard_' + key,
                                        quote(val, safe=''), quote(val, safe='')]))
        if auto_tone:
            rows.append('\t'.join([pid, quote(p['path'], safe=''), 'Action_AutoTone', '1', '1']))
        for key, value in sorted(changed.items()):
            rows.append('\t'.join([pid, quote(p['path'], safe=''), key,
                                    quote(scalar(value), safe=''), quote(scalar(baseline[key]), safe='')]))
        if changed:
            presets[pid] = xmp('Local AI ' + pid, changed)
        report['ready'].append({'photo_id': pid, 'path': p['path'], 'reason': d['reason'],
                                'subject': subject, 'confidence': d['confidence'], 'auto_tone': auto_tone, 'settings': changed,
                                'face_assist': d.get('face_assist'), 'metrics': d.get('metrics'),
                                'scene_lighting': d.get('scene_lighting','uncertain'),
                                'policy_settings': {k:v for k,v in changed.items() if k in policy_keys},
                                'model_settings': {k:v for k,v in changed.items() if k not in policy_keys}})
    report['unanalysed'] = sorted(set(photos) - seen)
    return '\n'.join(rows) + '\n', presets, report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', required=True, type=Path)
    ap.add_argument('--decisions', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--include-review', action='store_true')
    args = ap.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
        decisions = json.loads(args.decisions.read_text(encoding='utf-8-sig'))
        plan, presets, report = compile_plan(manifest, decisions, args.include_review)
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / 'presets').mkdir()
        (args.out / 'plan.tsv').write_text(plan, encoding='utf-8', newline='\n')
        for pid, data in presets.items():
            (args.out / 'presets' / f'LocalAI-{pid}.xmp').write_bytes(data)
        (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Ready: {len(presets)}; skipped: {len(report["skipped"])}; unanalysed: {len(report["unanalysed"])}; output: {args.out}')
    except (ValueError, KeyError, TypeError, OSError) as exc:
        ap.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
