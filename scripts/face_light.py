"""Local YuNet detection and rendered face-region measurements; no identity recognition."""
import base64
import io
from pathlib import Path
import sys
import statistics

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def histogram_stats(hist):
    count = sum(hist)
    def pct(q):
        total = 0
        for i, n in enumerate(hist):
            total += n
            if total >= count*q:
                return i
        return 255
    return {'luma_p50': pct(.5), 'luma_p65': pct(.65), 'luma_p90': pct(.9),
            'dark_fraction': round(sum(hist[:65])/max(1,count), 4),
            'near_white_fraction': round(sum(hist[250:])/max(1,count), 4)}


def skin_samples(image, box, landmarks):
    """Landmark-guided skin candidates, not a semantic skin segmentation model.

    Cheeks sit below the eye/lens band. Broad chroma/luma rejection removes many
    hair/lens/background pixels; coverage and agreement determine whether to use them.
    """
    x1,y1,x2,y2 = box
    w,h = x2-x1,y2-y1
    points = [(float(landmarks[i]), float(landmarks[i+1])) for i in range(0,10,2)]
    valid = all(x1 <= x <= x2 and y1 <= y <= y2 for x,y in points)
    eyes = sorted(points[:2])
    if valid and eyes[1][0]-eyes[0][0] > w*.15:
        ex,ey = (eyes[0][0]+eyes[1][0])/2,(eyes[0][1]+eyes[1][1])/2
        dx,dy = eyes[1][0]-eyes[0][0],eyes[1][1]-eyes[0][1]
        norm = (dx*dx+dy*dy)**.5
        ux,uy = dx/norm,dy/norm
        vx,vy = -uy,ux
        mouth_y = (points[3][1]+points[4][1])/2
        down = max(h*.28,min(h*.40,mouth_y-ey-h*.04))
        centers = [('left_cheek',eyes[0][0]+vx*down,eyes[0][1]+vy*down,w*.105,h*.075),
                   ('right_cheek',eyes[1][0]+vx*down,eyes[1][1]+vy*down,w*.105,h*.075),
                   ('forehead',ex-vx*h*.19,ey-vy*h*.19,w*.14,h*.065)]
    else:
        # Fallback regions are logged but not trusted for measurement-driven fill.
        centers = [('left_cheek',x1+w*.25,y1+h*.69,w*.10,h*.075),
                   ('right_cheek',x1+w*.75,y1+h*.69,w*.10,h*.075),
                   ('forehead',x1+w*.5,y1+h*.19,w*.14,h*.065)]
        valid = False
    crop = image.crop(box).convert('RGB')
    ycbcr = crop.convert('YCbCr')
    luminance = crop.convert('L')
    def pixels(im):
        return im.get_flattened_data() if hasattr(im,'get_flattened_data') else im.getdata()
    patches, total_hist = [], [0]*256
    for name,cx,cy,rx,ry in centers:
        mask = Image.new('L',crop.size)
        ImageDraw.Draw(mask).ellipse((cx-x1-rx,cy-y1-ry,cx-x1+rx,cy-y1+ry),fill=255)
        hist, geometric, kept = [0]*256,0,0
        for (r,g,b),(_,cb,cr),lum,inside in zip(pixels(crop),pixels(ycbcr),pixels(luminance),pixels(mask)):
            if not inside:
                continue
            geometric += 1
            if lum >= 25 and 75 <= cb <= 145 and 122 <= cr <= 185 and r >= g*.85 and r >= b*.85:
                hist[lum] += 1
                kept += 1
        coverage = kept/max(1,geometric)
        reliable = valid and kept >= 12 and coverage >= .45
        patch = {'name':name,'ellipse':[round(v,1) for v in (cx,cy,rx,ry)],
                 'candidate_pixels':kept,'coverage':round(coverage,3),'reliable':reliable,
                 **histogram_stats(hist)}
        patches.append(patch)
        if reliable:
            total_hist = [a+b for a,b in zip(total_hist,hist)]
    reliable = [p for p in patches if p['reliable']]
    # Require both cheeks, or a cheek plus forehead, to avoid one dark accessory.
    summary = histogram_stats(total_hist)
    if reliable:
        # Equal-weight regions: a large bright forehead must not drown out both dark cheeks.
        summary['luma_p50'] = statistics.median(p['luma_p50'] for p in reliable)
        summary['luma_p65'] = statistics.median(p['luma_p65'] for p in reliable)
        summary['luma_p90'] = max(p['luma_p90'] for p in reliable)
    return {'method':'landmark_skin_candidates_v1','landmarks_valid':valid,
            'regions':patches,'reliable_regions':len(reliable),
            'dark_regions':sum(p['luma_p65']<120 for p in reliable),
            **summary}


def measure_faces(image, detections):
    """Measure central elliptical face regions, excluding much of the hair/background.

    JPEG luma is a supporting observation, not a skin-tone/exposure ground truth.
    Coordinates refer to the resized, orientation-corrected analysis image.
    """
    faces = []
    for row in detections:
        x, y, w, h = map(float, row[:4])
        score = float(row[-1])
        if score < 0.85 or min(w, h) < 28 or w * h < image.width * image.height * 0.0015:
            continue
        box = (max(0, int(x)), max(0, int(y)),
               min(image.width, int(x+w)), min(image.height, int(y+h)))
        if min(box[2]-box[0],box[3]-box[1]) < 28:
            continue
        crop = image.crop(box).convert('L')
        mask = Image.new('L', crop.size)
        ImageDraw.Draw(mask).ellipse((crop.width*.18, crop.height*.25,
                                     crop.width*.82, crop.height*.88), fill=255)
        hist = crop.histogram(mask=mask)
        skin = skin_samples(image,box,row[4:14])
        central = histogram_stats(hist)
        headline = {k:skin[k] for k in central} if skin['reliable_regions'] >= 2 else central
        faces.append({'box': list(box), 'confidence': round(score, 3),
                      'area_fraction': round(w*h/(image.width*image.height), 5),
                      **headline,'central_luma':central,'skin_samples':skin})
    faces.sort(key=lambda f: f['area_fraction'], reverse=True)
    # Ignore distant bystanders when a larger subject is present; cap group/crop cost.
    faces = [f for f in faces if f['area_fraction'] >= faces[0]['area_fraction']*.25][:8] if faces else []
    background_mask = Image.new('L', image.size, 255)
    draw = ImageDraw.Draw(background_mask)
    for face in faces:
        draw.rectangle(tuple(face['box']), fill=0)
    background = image.convert('L').histogram(mask=background_mask)
    count = sum(background)
    accum, median = 0, 0
    for i, n in enumerate(background):
        accum += n
        if accum >= count*.5:
            median = i
            break
    for face in faces:
        face['background_minus_face'] = median-face['luma_p65']
        skin = face['skin_samples']
        face['dark_evidence'] = (skin['reliable_regions'] >= 2 and skin['dark_regions'] >= 2 and
                                 face['luma_p65'] < 115 and
                                 (face['background_minus_face'] > 30 or face['luma_p65'] < 70))
    return {'status': 'detected' if faces else 'no_reliable_face', 'detector': 'YuNet-2023mar',
            'faces': faces, 'background_luma_p50': median,
            'dark_face_count': sum(f['dark_evidence'] for f in faces)}


def detect_faces(image):
    # Dependencies are isolated from the user's system Python/site packages.
    deps = ROOT/'python_deps'
    if not deps.is_dir():
        deps = Path(r'C:\AI\LightroomLocalDevelop\python_deps')
    if sys.prefix == sys.base_prefix and deps.is_dir() and str(deps) not in sys.path:
        sys.path.insert(0, str(deps))
    try:
        import cv2
        import numpy as np
        model = ROOT/'models/face_detection_yunet_2023mar.onnx'
        if not model.is_file():
            model = Path(r'C:\AI\LightroomLocalDevelop\models\face_detection_yunet_2023mar.onnx')
        if not model.is_file():
            raise FileNotFoundError('YuNet model missing')
        detector = cv2.FaceDetectorYN.create(str(model), '', image.size, .85, .3, 5000)
        _, detections = detector.detect(cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR))
        return measure_faces(image, [] if detections is None else detections)
    except Exception as exc:
        raise RuntimeError('本地人臉檢查無法啟動；停止第二階段，請檢查 python_deps 與 YuNet 模型。 '+str(exc)) from exc


def face_sheet(image, metrics):
    faces = metrics['faces']
    if not faces:
        return None
    sheet = Image.new('RGB', (256*min(4, len(faces)), 256*((len(faces)+3)//4)), '#666666')
    for i, face in enumerate(faces):
        x1, y1, x2, y2 = face['box']
        pad = int(max(x2-x1, y2-y1)*.15)
        crop = image.crop((max(0, x1-pad), max(0, y1-pad),
                           min(image.width, x2+pad), min(image.height, y2+pad)))
        crop.thumbnail((240, 228))
        x, y = (i%4)*256, (i//4)*256
        sheet.paste(crop, (x+(256-crop.width)//2, y+24))
        ImageDraw.Draw(sheet).text((x+8, y+5), 'Face '+str(i+1), fill='white')
    data = io.BytesIO()
    sheet.save(data, format='JPEG', quality=90)
    return base64.b64encode(data.getvalue()).decode('ascii')


def face_adjustments(result, stats):
    """Combine AI judgement and measured evidence. Never brighten solely from skin luma."""
    metrics = stats.get('face_analysis', {})
    lighting = result.get('face_lighting', 'uncertain')
    info = {'model_judgement': lighting, 'added_deltas': {}, 'review_reason': ''}
    if result['subject'] != 'portrait':
        return info
    if metrics.get('status') != 'detected':
        info['review_reason'] = '人像未取得可靠臉部量測，請確認臉部亮度。'
        return info
    dark = [f for f in metrics['faces'] if f['dark_evidence']]
    if lighting == 'intentional':
        return info
    if lighting in ('uncertain', 'not_applicable'):
        info['review_reason'] = '模型無法確定臉部光線意圖，請確認。'
    elif dark and lighting in ('underexposed', 'adequate'):
        if any(f['luma_p90'] >= 235 or f['near_white_fraction'] >= .005 for f in metrics['faces']):
            info['review_reason'] = '同張人像同時有暗臉與接近過曝的臉，需局部處理；略過全圖微調。'
            return info
        # User's face-brightness preference: measured skin may trigger mild fill even
        # when the VLM calls it adequate; keep deliberate darkness and uncertainty gated.
        darkest = min(f['luma_p65'] for f in dark)
        floor = (40 if darkest < 70 else 25) if lighting == 'underexposed' else 15
        info['basis'] = 'ai_and_skin_agree' if lighting == 'underexposed' else 'measured_skin_fill_preference'
        if result['deltas'].get('Shadows2012', 0) < floor:
            info['added_deltas']['Shadows2012'] = floor
        balance = -15 if stats.get('rendered_luma_p99', 0) >= 245 else -10
        if result['deltas'].get('Highlights2012', 0) > balance:
            info['added_deltas']['Highlights2012'] = balance
    return info
