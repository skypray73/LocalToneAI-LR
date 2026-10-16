"""Offline photo analysis via a downloaded Ollama vision model on loopback only."""
import argparse
import base64
import io
import json
import math
from pathlib import Path
import time
import urllib.request
from PIL import Image, ImageOps
from build_plan import compile_plan, RANGES
from face_light import detect_faces, face_sheet, face_adjustments

DELTAS = {'Exposure2012': (-0.5, 0.5), 'Contrast2012': (-10, 10),
          'Highlights2012': (-70, 70), 'Shadows2012': (-70, 70),
          'Whites2012': (-25, 25), 'Blacks2012': (-25, 25),
          'Vibrance': (-10, 10), 'Saturation': (-10, 10)}
STEPS = {key: ([x / 10 for x in (-5, -3, -2, -1, 0, 1, 2, 3, 5)] if key == 'Exposure2012'
               else [x for x in (-70,-60,-50,-40,-30,-25,-20,-15,-10,-5,0,5,10,15,20,25,30,40,50,60,70) if bounds[0] <= x <= bounds[1]])
         for key, bounds in DELTAS.items()}
STEPS['Shadows2012'] = [-100,-90,-80] + STEPS['Shadows2012'] + [80,90,100]
SCHEMA = {'type': 'object', 'additionalProperties': False,
    'properties': {
        'subject': {'type': 'string', 'enum': ['portrait', 'landscape', 'other']},
        'scene_lighting': {'type': 'string', 'enum': ['day_or_indoor', 'night', 'uncertain']},
        'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']},
        'needs_review': {'type': 'boolean'},
        'reason': {'type': 'string', 'maxLength': 80},
        'face_lighting': {'type': 'string', 'enum': ['underexposed', 'adequate', 'intentional', 'uncertain', 'not_applicable']},
        'deltas': {'type': 'object', 'additionalProperties': False,
            'properties': {k: {'type': 'number', 'enum': STEPS[k]} for k in DELTAS},
            'required': list(DELTAS)},
    }, 'required': ['subject', 'scene_lighting', 'confidence', 'needs_review', 'reason', 'face_lighting', 'deltas']}
SYSTEM = '''You are a conservative photo editor. Analyse the supplied Lightroom-rendered preview.
Return only the requested JSON schema. Classify the main subject: portrait (people are the main
subject), landscape (scenery is the main subject), or other. People appearing in a travel scene
does NOT make it a portrait. Classify portrait only when the person/group is the primary subject.
If classification is uncertain,
set needs_review=true and confidence=low. Preserve intentional night scenes, silhouettes,
stage lighting, sunset warmth, deep blacks and high-key scenes. Histogram statistics describe
this rendered JPEG, not recoverable RAW detail. Do not equalise every image to medium brightness.
Propose small DELTAS to the CURRENT develop settings, not absolute values. Zero/no fields is valid.
Do not sharpen portraits. Preserve the exported landscape sharpening. Do not use texture or
clarity to boost detail on portraits. The program sets landscape Clarity and Dehaze to absolute
+20 per user preference, preserving sharpening. Do not return those keys or compensate for
this preference. Preserve Lightroom Auto's Vibrance and Saturation results: return both
colour deltas as 0. For portraits only, the program conservatively reduces positive Auto
Vibrance to about 70% and sets sharpening amount to 0; do not force Vibrance to 0.
Leave white balance, profile, crop, masks, denoise and sharpening
to the deterministic policy. Do not invent lost highlight detail. Judge main-subject exposure and
skin colour visually; image-wide brightness is only supporting information. Write reason in
Traditional Chinese, one short sentence of at most 40 characters. When pipeline_stage is
after-lightroom-auto, this preview ALREADY has Lightroom automatic tone correction applied.
Judge that corrected result and propose conservative
additional deltas when needed: main-subject brightness, unnatural contrast, overly lifted shadows,
highlight preservation, and skin colour. Give special attention to bright/dark detail: use
meaningful highlight/shadow corrections up to 70 points when needed, rather than routinely
choosing all zeros. Do not blindly apply maximum values. Protect highlights while opening
shadows; retain local contrast, do not flatten blacks or brighten highlights into clipping.
For a person/group that is the main subject, prioritise comfortably visible face brightness,
eyes and natural skin tone over image-average brightness or a perfectly bright background.
If faces are visibly too dark, prefer lifting Shadows, including +30 to +70 when warranted,
and lowering Highlights to balance a bright background. Use a small positive Exposure only
when highlight headroom permits. Do not accept dark faces merely because the scene looks
balanced overall. Do not brighten already well-exposed skin, wash out facial texture, or
change intentional silhouettes. These are global controls, not a face mask: avoid lifting
the entire background or flattening blacks solely to brighten a tiny distant face. Explain
face-lighting problems briefly in reason when people are the primary subject.
Classify scene_lighting as night only for an actual outdoor night scene, not merely a dark
daylight image or dim indoor lighting. Use uncertain when ambiguous. For night scenes only,
Shadows delta may range from -100 to +100 (day/other remains -70 to +70). Choose +80 to +100
only when needed to reveal useful dark detail. Preserve the night atmosphere, natural blacks,
light sources and silhouettes; do not turn night into daylight or blindly lift noise.
Highlights remain limited to +/-70; exposure and clipping protections are unchanged.
The first image is the full composition. If present, the second image is a numbered face
contact sheet in the same order as face_analysis.faces. Inspect these enlarged faces.
Set face_lighting to underexposed, adequate, intentional (deliberately dark faces), uncertain,
or not_applicable (not a portrait). Measured face luma is NOT a universal skin brightness
target: consider natural skin tone, sunglasses, shadows and intended lighting visually.
face_analysis.faces.skin_samples records cheek and forehead candidate regions guided by
eye/mouth landmarks, excluding the eye/lens band. These are geometric colour-filtered
candidates, not guaranteed skin segmentation. Use reliable_regions, coverage and each
region's brightness; do not mistake dark sunglasses for dark skin. The user's preference
allows a mild shadow fill when multiple reliable skin regions are dark against a brighter
background, even if you consider overall exposure adequate. Deliberate silhouettes and
uncertain intent still must not be automatically filled.
The user requests sufficiently bright faces in ordinary portraits. Sunglasses, backlighting,
hat shadows or standing in shade are NOT evidence of intentional darkness. Inspect visible
cheeks, forehead and lower face, not the dark lenses. Use intentional ONLY for unmistakable
creative silhouettes with deliberately hidden facial detail or deliberate theatrical low-key
lighting; never invent photographic intent to excuse underexposed faces in daylight portraits.
If dark_evidence is true, explicitly reassess the face crops instead of assuming the
image-wide Auto result is sufficient. Underexposed faces call for positive Shadows;
pair with negative Highlights when the background is bright. Do not lower exposure or
shadows further for dark faces unless their darkness is intentional or highlights require it.
If rendered_luma_p99 >= 245 or near_white_fraction >= 0.005, do NOT propose positive exposure,
whites or highlights. Lower highlights if existing bright areas lose texture. Never claim to
recover missing detail from already clipped pixels. Do not repeat a full automatic correction. Zero is valid
only if the corrected image genuinely needs no further change. Do not explain reasoning at
length. Use exactly the eight delta keys from the schema, each once; select one allowed value
per key, use 0 for unchanged. User style is a preference, never permission to break limits.'''


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Local-only mode refuses HTTP redirects')


def api(route, payload=None, timeout=180):
    # Ignore system proxies; pictures are only sent to this computer's loopback service.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:11434' + route, data=data,
                                 headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=timeout) as response:
        return json.load(response)


def preview_data(path):
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert('RGB')
        if all(hi - lo <= 1 for lo, hi in image.getextrema()):
            raise ValueError('分析預覽為空白／單一純色，未送入模型；請重新從 Lightroom 轉存預覽。')
        image.thumbnail((1024, 1024))
        sample = image.copy()
        sample.thumbnail((512, 512))
        hist = sample.convert('L').histogram()
        count = sum(hist)
        def percentile(q):
            accum = 0
            for index, n in enumerate(hist):
                accum += n
                if accum >= count * q:
                    return index
            return 255
        stats = {'rendered_luma_p01': percentile(0.01), 'rendered_luma_p50': percentile(0.5),
                 'rendered_luma_p99': percentile(0.99),
                 'near_black_fraction': round(sum(hist[:6]) / count, 5),
                 'near_white_fraction': round(sum(hist[250:]) / count, 5),
                 'width': image.width, 'height': image.height}
        data = io.BytesIO()
        # Fresh RGB JPEG strips EXIF/GPS; the manifest/paths never enter the model prompt.
        image.save(data, format='JPEG', quality=90)
    return base64.b64encode(data.getvalue()).decode('ascii'), stats


def convert_result(photo, result, stats):
    if result.get('subject') not in ('portrait', 'landscape', 'other'):
        raise ValueError('Invalid subject classification')
    if result.get('confidence') not in ('high', 'medium', 'low'):
        raise ValueError('Invalid confidence')
    if not isinstance(result.get('needs_review'), bool) or not isinstance(result.get('reason'), str) or not result['reason'].strip():
        raise ValueError('Missing reason/review flag')
    if not isinstance(result.get('deltas'), dict):
        raise ValueError('Invalid deltas')
    # Validate before using the face-assisted floor; malformed values must never be hidden.
    for key, delta in result['deltas'].items():
        if key not in DELTAS or isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(delta):
            raise ValueError('Unsupported/nonfinite model delta: ' + key)
    assist = face_adjustments(result, stats) if 'face_analysis' in stats else {
        'model_judgement': result.get('face_lighting', 'uncertain'), 'added_deltas': {}, 'review_reason': ''}
    deltas = dict(result['deltas'], **assist['added_deltas'])
    settings, notes = {}, []
    highlight_risk = stats.get('rendered_luma_p99',0) >= 245 or stats.get('near_white_fraction',0) >= 0.005
    if assist.get('basis') and stats.get('rendered_luma_p99',0) >= 235:
        highlight_risk = True  # Prefer shadow fill over global exposure when the sky is already bright.
    protected = []
    for key, delta in deltas.items():
        if key not in DELTAS or isinstance(delta, bool) or not isinstance(delta, (int, float)) or not math.isfinite(delta):
            raise ValueError('Unsupported/nonfinite model delta: ' + key)
        if key in ('Vibrance','Saturation'):
            continue
        baseline = photo['settings'].get(key)
        if isinstance(baseline, bool) or not isinstance(baseline, (int, float)) or not math.isfinite(baseline):
            notes.append('Missing baseline: ' + key)
            continue
        lo, hi = (-100, 100) if key == 'Shadows2012' and result.get('scene_lighting') == 'night' else DELTAS[key]
        bounded = max(lo, min(hi, delta))
        if bounded != delta:
            notes.append('Bounded delta: ' + key)
        if highlight_risk and key in ('Exposure2012','Whites2012','Highlights2012') and bounded>0:
            protected.append(key)
            bounded=0
        minimum, maximum = RANGES[key]
        value = round(max(minimum, min(maximum, baseline + bounded)), 3)
        if value != baseline:
            settings[key] = value
    review = result['needs_review'] or result['confidence'] == 'low' or bool(notes) or bool(assist['review_reason'])
    reason = result['reason']
    if assist['added_deltas']:
        reason += ('；依可見皮膚量測與臉部提亮偏好補光。' if assist.get('basis') == 'measured_skin_fill_preference'
                   else '；AI 與可見皮膚量測確認偏暗，補強陰影。')
    if assist['review_reason']:
        reason += '；'+assist['review_reason']
    return {'photo_id': str(photo['photo_id']), 'path': photo['path'],
            'subject': result['subject'], 'confidence': result['confidence'],
            'scene_lighting': result.get('scene_lighting','uncertain'),
            'status': 'needs_review' if review else 'ready',
            'reason': reason, 'settings': settings, 'notes': notes, 'metrics': stats,
            'face_assist': assist, 'highlight_protection': protected}


def request_result(request):
    """Retry an incomplete/transient model reply once, with a larger output budget."""
    for attempt in range(2):
        payload = dict(request, options=dict(request['options'], num_predict=768 if attempt == 0 else 1536))
        try:
            response = api('/api/chat', payload)
            if response.get('done') is not True or response.get('done_reason') == 'length':
                raise ValueError('Model response incomplete')
            result = json.loads(response['message']['content'])
            if not isinstance(result, dict):
                raise ValueError('Model JSON must be an object')
            return result
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if attempt:
                raise
            print('Local response unavailable/incomplete; retrying once: '+str(exc), flush=True)


def analyze_photo(photo, preview, model, style):
    image, stats = preview_data(preview)
    with Image.open(io.BytesIO(base64.b64decode(image))) as opened:
        picture = opened.convert('RGB')
    stats['face_analysis'] = detect_faces(picture)
    crops = face_sheet(picture, stats['face_analysis'])
    safe_baseline = {k: v for k, v in photo['settings'].items() if k in DELTAS}
    request = {'model': model, 'stream': False, 'format': SCHEMA, 'keep_alive': '5m',
        'options': {'temperature': 0, 'num_ctx': 6144, 'num_predict': 768},
        'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user',
            'content': json.dumps({'style': style, 'pipeline_stage': photo.get('pipeline_stage','current-develop'),
                                  'baseline': safe_baseline, 'image_statistics': stats}, ensure_ascii=False),
            'images': [image, crops] if crops else [image]}]}
    result = request_result(request)
    # One bounded second look at contradictory dark-face judgements, using the same local images.
    if (result.get('subject') == 'portrait' and stats['face_analysis']['dark_face_count'] and
            result.get('face_lighting') in ('adequate', 'not_applicable', 'uncertain', 'intentional')):
        request['messages'][1]['content'] += ('\nRecheck the enlarged faces: central face regions are dark. '
            'Decide whether this is natural skin tone/intentional lighting or underexposure. '
            'If underexposed, propose positive Shadows with highlight protection. '
            'Do not repeat adequate only because the full background is bright. Sunglasses or '
            'ordinary daylight/backlit shadows do not justify intentional darkness. The user wants '
            'the visible skin on cheeks and lower face comfortably bright. Only a clear creative '
            'silhouette or theatrical lighting justifies intentional. Describe the visible evidence.')
        result = request_result(request)
        result['face_rechecked'] = True
    return convert_result(photo, result, stats), result


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def write_progress(folder, done, total, stage):
    (folder / 'progress.tsv').write_text(f'LRPROGRESS\t1\t{done}\t{total}\t{stage}\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', default='qwen3-vl:8b-instruct')
    parser.add_argument('--style', default='自然修圖，保留拍攝氣氛與膚色')
    args = parser.parse_args()
    try:
        if 'cloud' in args.model.lower():
            raise ValueError('Cloud models forbidden in local-only mode')
        models = api('/api/tags', timeout=10).get('models', [])
        if not any(m.get('name') == args.model and not m.get('remote_host') for m in models):
            raise ValueError('Model must already be downloaded locally: ' + args.model)
        manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
        if manifest.get('version') != 1 or not manifest.get('catalog'):
            raise ValueError('Require a plugin manifest, version 1')
        root = args.manifest.resolve().parent
        # Validate identities before inference, without uploading or downloading anything.
        compile_plan(manifest, {'photos': []})
        args.out.mkdir(parents=True, exist_ok=False)
        decisions = {'style': args.style, 'source': 'local-ollama', 'model': args.model, 'photos': []}
        failures = []
        for index, photo in enumerate(manifest['photos'], 1):
            photo = dict(photo, pipeline_stage=manifest.get('pipeline_stage','current-develop'))
            started = time.monotonic()
            write_progress(args.out, index - 1, len(manifest['photos']), 'analysing')
            print(f'[{index}/{len(manifest["photos"])}] ID {photo["photo_id"]}: starting local inference', flush=True)
            try:
                preview = (root / photo['preview']).resolve()
                if not preview.is_relative_to(root):
                    raise ValueError('Preview must stay inside the batch folder')
                decision, raw = analyze_photo(photo, preview, args.model, args.style)
                # The plugin already performed Lightroom auto tone before exporting this preview.
                # Keep the model's additional deltas, computed relative to the corrected baseline.
                decision['auto_tone'] = False
                # Enforce final sharpening policy and baseline constraints immediately.
                compile_plan(manifest, {'photos': [decision]})
                decisions['photos'].append(decision)
                write_json(args.out / f'analysis-{photo["photo_id"]}.json', raw)
                print(f'[{index}/{len(manifest["photos"])}] ID {photo["photo_id"]}: {decision["subject"]}, {decision["status"]}, {time.monotonic()-started:.1f}s', flush=True)
            except Exception as exc:
                failures.append({'photo_id': str(photo['photo_id']), 'error': str(exc)})
                print(f'[{index}/{len(manifest["photos"])}] ID {photo["photo_id"]}: FAILED: {exc}', flush=True)
            write_json(args.out / 'decisions.json', decisions)
            write_json(args.out / 'failures.json', failures)
            write_progress(args.out, index, len(manifest['photos']), 'analysing')
        plan, presets, report = compile_plan(manifest, decisions)
        (args.out / 'presets').mkdir()
        (args.out / 'plan.tsv').write_text(plan, encoding='utf-8', newline='\n')
        for pid, data in presets.items():
            (args.out / 'presets' / f'LocalAI-{pid}.xmp').write_bytes(data)
        report.update({'source': 'local-ollama', 'model': args.model, 'failures': failures})
        write_json(args.out / 'report.json', report)
        write_progress(args.out, len(manifest['photos']), len(manifest['photos']), 'complete')
        print(f'Complete: {len(report["ready"])} ready, {len(report["skipped"])} skipped, {len(failures)} failures. Lightroom apply/visual verification pending.', flush=True)
        if failures:
            parser.exit(1, 'Partial analysis; see failures.json. Failed photos are not in the plan.\n')
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
