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
