# -*- coding: utf-8 -*-
"""
يولّد فيديوهات اختبار بصيغة Y4M تُغذّى لـ Chrome ككاميرا وهمية:
  chrome --use-fake-device-for-media-stream --use-fake-ui-for-media-stream --use-file-for-fake-video-capture=FILE.y4m
كل فيديو يمثل سيناريو حقيقياً واجهناه في التجارب الميدانية.
التشغيل: python tests/make_videos.py   (يكتب إلى tests/out/)
يحتاج: numpy, pillow
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out'); os.makedirs(OUT, exist_ok=True)
SCENES = os.path.join(HERE, 'scenes')
sys.path.insert(0, os.path.join(HERE, '..', '..', 'archive', 'nvr-python'))


def write_y4m(name, frames, fps=4):
    W, H = frames[0].size
    with open(os.path.join(OUT, name), 'wb') as f:
        f.write(b'YUV4MPEG2 W%d H%d F%d:1 Ip A1:1 C420jpeg\n' % (W, H, fps))
        for im in frames:
            y = np.asarray(im.convert('YCbCr'))
            f.write(b'FRAME\n'); f.write(y[..., 0].tobytes()); f.write(y[::2, ::2, 1].tobytes()); f.write(y[::2, ::2, 2].tobytes())
    print('wrote', name, len(frames), 'frames')


def noisy(rng, img, sigma=4, gain=1.0):
    a = np.asarray(img).astype(np.float32) * gain + rng.normal(0, sigma, (img.size[1], img.size[0], 3))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def live():
    """عارضة افتراضية: يد تشيل منتجاً، يبقى غائباً ~25 ث ثم يرجع (يُفترض: نقص ← تنبيه ← إغلاق تلقائي بالرجوع)."""
    from demo import DemoScene
    s = DemoScene(21); fr = []
    for k in range(200):
        s.present[1] = not (42 <= k < 142)
        im = s.render()
        if 40 <= k < 44 or 140 <= k < 144:
            d = ImageDraw.Draw(im); d.ellipse([250 + (k % 4) * 20, 60, 520, 330], fill=(200, 150, 120)); d.rectangle([380, 250, 700, 720], fill=(60, 80, 140))
        fr.append(im.resize((640, 360), Image.BILINEAR))
    write_y4m('live.y4m', fr)


def gum():
    """علكة صغيرة على طاولة خشب، يد تشيلها (يُفترض: نقص ← تنبيه)."""
    rng = np.random.default_rng(3); W, H = 640, 360
    yy, xx = np.mgrid[0:H, 0:W]
    wood = 150 + 18 * np.sin(xx / 7 + np.sin(yy / 30) * 2) + 6 * np.sin(yy / 2.5)
    base = np.stack([wood, wood * 0.72, wood * 0.5], -1)
    def frame(g, hand=None):
        a = base.copy()
        if g:
            gx, gy = 300, 170
            a[gy:gy + 12, gx:gx + 32] = [230, 232, 236]; a[gy:gy + 12, gx:gx + 2] = 60; a[gy:gy + 12, gx + 30:gx + 32] = 60
            a[gy:gy + 2, gx:gx + 32] = 60; a[gy + 10:gy + 12, gx:gx + 32] = 60; a[gy + 4:gy + 7, gx + 6:gx + 26] = [40, 90, 190]
        im = Image.fromarray(np.clip(a * rng.uniform(.96, 1.04) + rng.normal(0, 6, a.shape), 0, 255).astype(np.uint8))
        if hand: d = ImageDraw.Draw(im); d.ellipse([hand, 120, hand + 160, 260], fill=(200, 150, 120)); d.rectangle([hand + 60, 200, hand + 260, 360], fill=(60, 80, 140))
        return im
    write_y4m('gum.y4m', [frame(True) for _ in range(24)] + [frame(i < 4, hand=200 + i * 10) for i in range(8)] + [frame(False) for _ in range(120)])


def _pair(name):
    im = Image.open(os.path.join(SCENES, name)); W = (im.size[0] - 10) // 2 if 'gum' in name else (im.size[0] - 8) // 2
    off = 10 if 'gum' in name else 8
    return im.crop((0, 0, W, im.size[1])), im.crop((W + off, 0, 2 * W + off, im.size[1]))


def user():
    """مشهد المستخدم الحقيقي (علكة + ماوس على لابتوب): يد تشيل الاثنين مع تغيّر تعريض الآيفون (يُفترض: نقصان)."""
    rng = np.random.default_rng(1); base, gone = _pair('gum_mouse_pair.png'); OW, OH = base.size
    def fr(img, gain=1.0, hand=None):
        out = noisy(rng, img, 4, gain)
        if hand is not None:
            d = ImageDraw.Draw(out); d.ellipse([hand, 180, hand + 170, 330], fill=(205, 160, 135)); d.rectangle([hand + 40, 300, hand + 260, OH], fill=(70, 70, 90))
        return out
    write_y4m('user.y4m', [fr(base) for _ in range(24)] + [fr(base if i < 3 else gone, 0.8, hand=60 + i * 15) for i in range(8)]
              + [fr(gone, 0.8 + 0.2 * min(1, i / 12)) for i in range(140)])
    # ذراع ثابتة فوق جزء من العارضة (مع كاشف أشخاص وهمي بلون الكم الأخضر) — يُفترض: لا إنذار
    rng = np.random.default_rng(2)
    def arm(img, on):
        out = img.copy()
        if on: d = ImageDraw.Draw(out); d.rectangle([0, 95, 85, 140], fill=(40, 140, 70)); d.ellipse([75, 92, 120, 138], fill=(205, 160, 135))
        return noisy(rng, out)
    write_y4m('arm.y4m', [arm(base, False) for _ in range(24)] + [arm(base, True) for _ in range(96)] + [arm(base, False) for _ in range(40)])
    # انزياح بسيط للكاميرا ثم شيل العلكة فقط — يُفترض: إنذار للعلكة فقط
    rng = np.random.default_rng(9)
    g = np.asarray(gone).copy(); b = np.asarray(base); g[:, 190:] = b[:, 190:]; gum_gone = Image.fromarray(g)
    mv = lambda img, dx, dy, rot: img.rotate(rot, resample=Image.BILINEAR, translate=(dx, dy), fillcolor=(30, 30, 40))
    hand = lambda im, x: (lambda c: (ImageDraw.Draw(c).ellipse([x, 150, x + 150, 290], fill=(205, 160, 135)), c)[1])(im.copy())
    seq = [noisy(rng, base) for _ in range(24)] + [noisy(rng, mv(base, 3, 2, .3)), noisy(rng, mv(base, 9, 6, 1.0))] + [noisy(rng, mv(base, 7, 5, .8)) for _ in range(54)]
    seq += [noisy(rng, hand(mv(base if i < 3 else gum_gone, 7, 5, .8), 40 + i * 12)) for i in range(8)] + [noisy(rng, mv(gum_gone, 7, 5, .8)) for _ in range(80)]
    write_y4m('nudge.y4m', seq)
    # ضربة كبيرة للكاميرا (14 بكسل + 2°) بدون شيل — يُفترض: إعادة ضبط بدون إنذار
    rng = np.random.default_rng(4)
    write_y4m('nudge2.y4m', [noisy(rng, base) for _ in range(24)] + [noisy(rng, mv(base, 8, 6, 1.0)), noisy(rng, mv(base, 18, 12, 2.5))] + [noisy(rng, mv(base, 14, 10, 2.0)) for _ in range(100)])


def focus():
    """رف حقيقي مع «تنفّس» تركيز الآيفون (تقريب 2% + ضبابية) كل 3 ث بدون أي شيل — يُفترض: لا إنذار."""
    rng = np.random.default_rng(5); base, soft = _pair('shelf_focus_pair.png')
    seq = []
    for c in range(14):
        src = base if c % 2 == 0 else soft
        seq += [noisy(rng, src, 3.5, 1.0 if c % 2 == 0 else .97) for _ in range(12)]
    write_y4m('focus.y4m', seq)


def steal():
    """هجمات تُخفي السرقة داخل «حركة الكاميرا» (تجربة ميدانية: بعد إصلاح الحركة البسيطة صار لا يكشف السرقة نهائياً)."""
    rng = np.random.default_rng(11); base, gone = _pair('gum_mouse_pair.png'); OW, OH = base.size
    g = np.asarray(gone).copy(); b = np.asarray(base); g[:, 190:] = b[:, 190:]; gum_gone = Image.fromarray(g)
    mv = lambda img, dx, dy, rot: img.rotate(rot, resample=Image.BILINEAR, translate=(dx, dy), fillcolor=(30, 30, 40))
    # 1) ذراع قريبة من الموبايل تملأ أغلب الصورة (تبدو «حركة كاميرا») وتأخذ العلكة — يُفترض: إنذار للعلكة
    def arm(img, x):
        out = img.copy(); d = ImageDraw.Draw(out)
        d.polygon([(x, 0), (x + 560, 0), (x + 460, OH), (x - 120, OH)], fill=(60, 64, 80)); d.ellipse([x + 60, 40, x + 420, 380], fill=(205, 160, 135))
        return out
    seq = [noisy(rng, base) for _ in range(24)] + [noisy(rng, arm(base if i < 10 else gum_gone, -300 + i * 30 if i < 10 else 0 - (i - 10) * 40)) for i in range(20)] + [noisy(rng, gum_gone) for _ in range(120)]
    write_y4m('reach.y4m', seq)
    # 2) دفع الموبايل قليلاً وأخذ العلكة في نفس اللحظة — يُفترض: إنذار للعلكة فقط (لا للماوس)
    rng = np.random.default_rng(12)
    hand = lambda im, x: (lambda c: (ImageDraw.Draw(c).ellipse([x, 150, x + 150, 290], fill=(205, 160, 135)), c)[1])(im.copy())
    seq = [noisy(rng, base) for _ in range(24)]
    seq += [noisy(rng, hand(mv(base if i < 3 else gum_gone, 2 * i, 1.5 * i, .2 * i), 40 + i * 12)) for i in range(6)]
    seq += [noisy(rng, mv(gum_gone, 10, 7, 1.0)) for _ in range(120)]
    write_y4m('bumpsteal.y4m', seq)


if __name__ == '__main__':
    live(); gum(); user(); focus(); steal()
