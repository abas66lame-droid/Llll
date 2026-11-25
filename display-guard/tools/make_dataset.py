#!/usr/bin/env python3
"""ملف تنبيهات (haris-cases-*.json) ← مجموعة بيانات: صور قبل/بعد/قص + labels.csv فيه عمود truth للتصحيح.
الاستخدام: python3 tools/make_dataset.py <cases.json> [<cases.json> ...] -o dataset/"""
import argparse, base64, csv, hashlib, json, os

ap = argparse.ArgumentParser()
ap.add_argument('files', nargs='+')
ap.add_argument('-o', '--out', default='dataset')
a = ap.parse_args()

img_dir = os.path.join(a.out, 'images')
os.makedirs(img_dir, exist_ok=True)
csv_path = os.path.join(a.out, 'labels.csv')
seen = set()
if os.path.exists(csv_path):
    with open(csv_path, encoding='utf-8') as f:
        seen = {r['id'] for r in csv.DictReader(f)}

cols = ['id', 'source', 't', 'zone', 'system_kind', 'status', 'x', 'y', 'w', 'h', 'pol', 'hand', 'note', 'truth']
new = 0
with open(csv_path, 'a', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=cols)
    if not seen:
        w.writeheader()
    for path in a.files:
        with open(path, encoding='utf-8-sig') as fh:
            data = json.load(fh)
        for c in data.get('cases', []):
            b = c.get('box') or {}
            cid = hashlib.sha1(f"{c.get('t')}|{b}|{c.get('kind')}".encode()).hexdigest()[:12]
            if cid in seen:
                continue
            seen.add(cid)
            for k in ('img_b', 'img_a', 'img_c'):
                if c.get(k, '').startswith('data:image'):
                    with open(os.path.join(img_dir, f'{cid}_{k[-1]}.jpg'), 'wb') as im:
                        im.write(base64.b64decode(c[k].split(',', 1)[1]))
            d = c.get('dbg') or {}
            w.writerow({'id': cid, 'source': os.path.basename(path), 't': c.get('t'), 'zone': c.get('zone', ''),
                        'system_kind': c.get('kind'), 'status': c.get('status'),
                        'x': round(b.get('x', 0), 4), 'y': round(b.get('y', 0), 4), 'w': round(b.get('w', 0), 4), 'h': round(b.get('h', 0), 4),
                        'pol': d.get('pol', ''), 'hand': d.get('hand', ''), 'note': c.get('note', ''), 'truth': ''})
            new += 1
print(f'{new} أمثلة جديدة → {csv_path} (المجموع {len(seen)})')

# رفع اختياري إلى Supabase: SUPABASE_URL و SUPABASE_KEY في البيئة (الجدول samples ومكان الصور samples)
URL, KEY = os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY')
if URL and KEY:
    import ssl, urllib.request, urllib.error
    ca = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE')
    ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
    H = {'apikey': KEY, 'Authorization': f'Bearer {KEY}'}

    def req(method, path, body, ctype, extra=None):
        r = urllib.request.Request(URL.rstrip('/') + path, data=body, method=method, headers={**H, 'Content-Type': ctype, **(extra or {})})
        try:
            with urllib.request.urlopen(r, context=ctx, timeout=60) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:200]
            if e.code == 409 or 'Duplicate' in msg:  # التخزين يردّ 400 بنص 409 للصورة المرفوعة سابقاً
                return 409
            raise RuntimeError(f'{e.code} {msg}')

    with open(csv_path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in 'bac':
            p = os.path.join(img_dir, f"{r['id']}_{k}.jpg")
            if os.path.exists(p):
                with open(p, 'rb') as im:
                    req('POST', f"/storage/v1/object/samples/{r['id']}_{k}.jpg", im.read(), 'image/jpeg')
    num = lambda v: float(v) if v not in ('', None) else None
    payload = [{**r, 't': num(r['t']), 'x': num(r['x']), 'y': num(r['y']), 'w': num(r['w']), 'h': num(r['h']), 'pol': num(r['pol']),
                'hand': {'True': True, 'False': False}.get(r['hand']), 'truth': r['truth'] or None} for r in rows]
    for r in payload:
        if r['truth'] is None:
            r.pop('truth')
    req('POST', '/rest/v1/samples?on_conflict=id', json.dumps(payload).encode(), 'application/json',
        {'Prefer': 'resolution=merge-duplicates,return=minimal'})
    print(f'رُفع {len(rows)} مثال وصورها إلى Supabase')
