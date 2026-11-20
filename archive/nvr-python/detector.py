# -*- coding: utf-8 -*-
"""
محرك كشف التغيّر في العارضات (للكاميرات الثابتة).

الفكرة: نقارن منطقة العارضة في الصورة الحالية مع "الصورة المرجعية" على شكل شبكة خلايا صغيرة.
لكل خلية نحسب:
  - تشابه البنية (ارتباط الإضاءة + ارتباط الحواف)
  - كمية التفاصيل (الحواف) قبل وبعد: نقصانها = منتج أُزيل وصار المكان فارغاً، زيادتها = منتج أُضيف
  - فرق اللون: يكشف استبدال منتج بآخر بنفس الشكل
ثم نجمع الخلايا المتجاورة إلى "مناطق" (نقص / إضافة / تبديل).
"""
import numpy as np
from PIL import Image


def to_arrays(img, width=960):
    """صورة PIL -> قنوات numpy (رمادي + لونين) بعرض ثابت."""
    img = img.convert('RGB')
    w, h = img.size
    if w != width:
        img = img.resize((width, max(1, round(h * width / w))), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    g = 0.299 * R + 0.587 * G + 0.114 * B
    return {'g': _blur3(g), 'ca': R - G, 'cb': (R + G) / 2 - B, 'img': img, 'w': img.size[0], 'h': img.size[1]}


def _blur3(g):
    p = np.pad(g, 1, mode='edge')
    return (p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:] + p[1:-1, :-2] + p[1:-1, 1:-1] + p[1:-1, 2:] + p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]) / 9.0


def _grad(g):
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1, :] = g[2:, :] - g[:-2, :]
    return np.hypot(gx, gy)


def _blocks(arr, cs, ny, nx):
    a = arr[:ny * cs, :nx * cs]
    return a.reshape(ny, cs, nx, cs).transpose(0, 2, 1, 3).reshape(ny, nx, cs * cs)


def _bncc(A, B):
    A = A - A.mean(-1, keepdims=True)
    B = B - B.mean(-1, keepdims=True)
    va = (A * A).sum(-1)
    vb = (B * B).sum(-1)
    num = (A * B).sum(-1)
    den = np.sqrt(va * vb)
    out = np.where(den > 1e-3, num / np.maximum(den, 1e-6), 0.0)
    out = np.where((va < 1e-3) & (vb < 1e-3), 1.0, out)
    return out


def _crop(arr, x0, y0, x1, y1, dx=0, dy=0):
    """قص مع إزاحة؛ يرجع None إذا خرج عن الصورة."""
    H, W = arr.shape
    xa, ya, xb, yb = x0 + dx, y0 + dy, x1 + dx, y1 + dy
    if xa < 0 or ya < 0 or xb > W or yb > H:
        return None
    return arr[ya:yb, xa:xb]


def estimate_shift(ref, cur, maxs=6):
    """تقدير اهتزاز الكاميرا (إزاحة صغيرة) بين صورتين."""
    a = _grad(ref['g'][::4, ::4])
    b = _grad(cur['g'][::4, ::4])
    m = 3
    best, bd = -2, (0, 0)
    A = a[m:-m, m:-m].ravel()
    A = A - A.mean()
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            Bc = b[m + dy:b.shape[0] - m + dy, m + dx:b.shape[1] - m + dx].ravel()
            Bc = Bc - Bc.mean()
            d = np.sqrt((A * A).sum() * (Bc * Bc).sum())
            c = (A * Bc).sum() / d if d > 0 else 0
            if c > best:
                best, bd = c, (dx * 4, dy * 4)
    return bd


def compare_zone(ref, cur, zone, shift=(0, 0)):
    """
    zone: dict x,y,w,h (نسب 0..1 من الصورة)
    يرجع: شبكة حالات الخلايا + المناطق المكتشفة (بإحداثيات الصورة النسبية)
    """
    W, H = ref['w'], ref['h']
    x0 = int(round(zone['x'] * W)); y0 = int(round(zone['y'] * H))
    x1 = int(round((zone['x'] + zone['w']) * W)); y1 = int(round((zone['y'] + zone['h']) * H))
    zw, zh = max(8, x1 - x0), max(8, y1 - y0)
    cs = int(max(10, min(40, round(zw / 20))))
    nx, ny = max(1, zw // cs), max(1, zh // cs)
    x1, y1 = x0 + nx * cs, y0 + ny * cs
    if x1 > W: x0 -= x1 - W; x1 = W
    if y1 > H: y0 -= y1 - H; y1 = H
    x0, y0 = max(0, x0), max(0, y0)

    rg = _crop(ref['g'], x0, y0, x1, y1)
    rgr = _grad(rg)
    R_g = _blocks(rg, cs, ny, nx); R_gr = _blocks(rgr, cs, ny, nx)
    tr = R_gr.mean(-1)
    ra = _blocks(_crop(ref['ca'], x0, y0, x1, y1), cs, ny, nx).mean(-1)
    rb = _blocks(_crop(ref['cb'], x0, y0, x1, y1), cs, ny, nx).mean(-1)
    rm = R_g.mean(-1)

    # نجرّب إزاحات صغيرة لتعويض الاهتزاز؛ نأخذ أفضل تشابه، وأقل/أكثر قيمة للتفاصيل حتى لا تخدعنا حافة مجاورة
    best_sim = np.full((ny, nx), -2.0)
    tmin = np.full((ny, nx), 1e9); tmax = np.zeros((ny, nx)); tb = np.zeros((ny, nx))
    md = np.full((ny, nx), 1e9); cd = np.full((ny, nx), 1e9)
    sdx, sdy = shift
    step = max(1, cs // 6)
    ok_any = False
    for dy in (-step, 0, step):
        for dx in (-step, 0, step):
            cg = _crop(cur['g'], x0, y0, x1, y1, dx + sdx, dy + sdy)
            if cg is None:
                continue
            ok_any = True
            cgr = _grad(cg)
            C_g = _blocks(cg, cs, ny, nx); C_gr = _blocks(cgr, cs, ny, nx)
            sim = 0.45 * _bncc(R_g, C_g) + 0.55 * _bncc(R_gr, C_gr)
            t = C_gr.mean(-1)
            tb = np.where(sim > best_sim, t, tb)
            best_sim = np.maximum(best_sim, sim)
            tmin = np.minimum(tmin, t); tmax = np.maximum(tmax, t)
            md = np.minimum(md, np.abs(C_g.mean(-1) - rm))
            ca = _blocks(_crop(cur['ca'], x0, y0, x1, y1, dx + sdx, dy + sdy), cs, ny, nx).mean(-1)
            cb = _blocks(_crop(cur['cb'], x0, y0, x1, y1, dx + sdx, dy + sdy), cs, ny, nx).mean(-1)
            cd = np.minimum(cd, np.hypot(ca - ra, cb - rb))
    if not ok_any:
        return {'cells': np.full((ny, nx), 'same', dtype='<U4'), 'regions': [], 'changed': 0.0, 'grid': (nx, ny)}
    tc = tb   # التفاصيل عند أفضل تطابق
    lo = np.maximum(tr, tc) < 4.0
    st = np.full((ny, nx), 'same', dtype='<U4')
    # النقص: الخلية كانت فيها تفاصيل (منتج) وصارت شبه فارغة. الإضافة: العكس.
    rem = (best_sim < 0.5) & (tmax < 0.55 * tr) & (tmax < 6.0) & (tr - tmax > 5) & ~lo
    add = (best_sim < 0.5) & (tr < 0.55 * tmin) & (tr < 6.0) & (tmin - tr > 5) & ~lo & ~rem
    textured = np.maximum(tr, tc) > 8.0
    # انخفاض التشابه وحده قد يكون بسبب تفاصيل دقيقة (كتابة) مع اهتزاز بسيط؛ نشترط معه اختلافاً فعلياً في التفاصيل أو اللون أو الإضاءة
    tex_diff = np.abs(tr - tc) / np.maximum(1.0, np.maximum(tr, tc))
    real = (tex_diff > 0.3) | (cd > 12) | (md > 20)
    chg = (~lo & ~rem & ~add & (((best_sim < 0.3) & textured & real) | (cd > 28) | (md > 45))) | (lo & ((md > 45) | (cd > 30)))
    st[rem] = 'rem'; st[add] = 'add'; st[chg] = 'chg'
    strong = (rem & (tmax < 0.38 * tr)) | (add & (tr < 0.38 * tmin))

    regions = _group(st, strong, nx, ny)
    out = []
    for r in regions:
        i0, j0, i1, j1 = r['box']
        out.append({'type': r['type'], 'cells': r['cells'],
                    'x': (x0 + i0 * cs) / W, 'y': (y0 + j0 * cs) / H,
                    'w': (i1 - i0 + 1) * cs / W, 'h': (j1 - j0 + 1) * cs / H})
    changed = float((st != 'same').mean())
    return {'cells': st, 'regions': out, 'changed': changed, 'grid': (nx, ny)}


def _group(st, strong, nx, ny):
    lab = -np.ones((ny, nx), dtype=int)
    comps = []

    def nb(j, i):
        for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            a, b = j + dj, i + di
            if 0 <= a < ny and 0 <= b < nx:
                yield a, b

    def grow(j, i, typ, ok):
        cid = len(comps); q = [(j, i)]; mem = []; lab[j, i] = cid
        while q:
            c = q.pop(); mem.append(c)
            for a, b in nb(*c):
                if lab[a, b] < 0 and ok(a, b):
                    lab[a, b] = cid; q.append((a, b))
        comps.append({'type': typ, 'mem': mem})

    for j in range(ny):
        for i in range(nx):
            if lab[j, i] < 0 and strong[j, i]:
                t = st[j, i]
                grow(j, i, t, lambda a, b, t=t: strong[a, b] and st[a, b] == t)
    for j in range(ny):
        for i in range(nx):
            if lab[j, i] < 0 and st[j, i] in ('rem', 'add') and not any(lab[a, b] >= 0 for a, b in nb(j, i)):
                t = st[j, i]
                grow(j, i, t, lambda a, b, t=t: st[a, b] == t)
    for _ in range(2):
        for j in range(ny):
            for i in range(nx):
                if lab[j, i] < 0 and st[j, i] != 'same':
                    for a, b in nb(j, i):
                        if lab[a, b] >= 0:
                            lab[j, i] = lab[a, b]; comps[lab[a, b]]['mem'].append((j, i)); break
    for j in range(ny):
        for i in range(nx):
            if lab[j, i] < 0 and st[j, i] == 'chg':
                grow(j, i, 'chg', lambda a, b: st[a, b] == 'chg' and lab[a, b] < 0)
    res = []
    for c in comps:
        if len(c['mem']) < (4 if c['type'] == 'chg' else 2):   # التبديل يحتاج مساحة أكبر لتجنّب الضوضاء
            continue
        js = [m[0] for m in c['mem']]; is_ = [m[1] for m in c['mem']]
        res.append({'type': c['type'], 'cells': len(c['mem']), 'box': (min(is_), min(js), max(is_), max(js))})
    return res


def motion(prev, cur, zone, block=16, thr=14.0):
    """فحص سريع للحركة داخل المنطقة: نسبة المربعات (16×16) التي تغيّر متوسط إضاءتها بوضوح بين لقطتين.
    نتسامح مع اهتزاز بسيط (±2 بكسل) ومع تغيّر الإضاءة العام."""
    W, H = prev['w'], prev['h']
    x0 = int(zone['x'] * W); y0 = int(zone['y'] * H)
    nx = max(1, int(zone['w'] * W) // block); ny = max(1, int(zone['h'] * H) // block)
    x1 = min(W - 2, x0 + nx * block); y1 = min(H - 2, y0 + ny * block)
    x0, y0 = max(2, x0), max(2, y0)
    nx, ny = (x1 - x0) // block, (y1 - y0) // block
    if nx < 1 or ny < 1:
        return 0.0
    x1, y1 = x0 + nx * block, y0 + ny * block
    a = _blocks(prev['g'][y0:y1, x0:x1], block, ny, nx).mean(-1)
    best = None
    for dy in (-2, 0, 2):
        for dx in (-2, 0, 2):
            b = _blocks(cur['g'][y0 + dy:y1 + dy, x0 + dx:x1 + dx], block, ny, nx).mean(-1)
            diff = b - a
            d = np.abs(diff - np.median(diff))
            best = d if best is None else np.minimum(best, d)
    return float((best > thr).mean()), int((best > thr).sum())


def region_similarity(ref, cur, box, shift=(0, 0)):
    """تشابه منطقة محددة بين صورتين (للتحقق من رجوع المنتج إلى مكانه)."""
    W, H = ref['w'], ref['h']
    x0 = max(0, int(box['x'] * W)); y0 = max(0, int(box['y'] * H))
    x1 = min(W, int((box['x'] + box['w']) * W)); y1 = min(H, int((box['y'] + box['h']) * H))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return 0.0
    a = ref['g'][y0:y1, x0:x1]
    best = -1.0
    for dy in (-3, 0, 3):
        for dx in (-3, 0, 3):
            b = _crop(cur['g'], x0, y0, x1, y1, dx + shift[0], dy + shift[1])
            if b is None:
                continue
            A = a.ravel() - a.mean(); Bv = b.ravel() - b.mean()
            ga = _grad(a).ravel(); gb = _grad(b).ravel(); ga = ga - ga.mean(); gb = gb - gb.mean()
            d1 = np.sqrt((A * A).sum() * (Bv * Bv).sum()); d2 = np.sqrt((ga * ga).sum() * (gb * gb).sum())
            s = 0.45 * ((A * Bv).sum() / d1 if d1 > 0 else 0) + 0.55 * ((ga * gb).sum() / d2 if d2 > 0 else 0)
            best = max(best, s)
    return float(best)


def overlap(a, b):
    ix = max(0.0, min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x']))
    iy = max(0.0, min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y']))
    return ix * iy / max(1e-9, min(a['w'] * a['h'], b['w'] * b['h']))
