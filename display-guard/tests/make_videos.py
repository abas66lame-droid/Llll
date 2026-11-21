# -*- coding: utf-8 -*-
"""
يولّد فيديوهات اختبار بصيغة Y4M تُغذّى لـ Chrome ككاميرا وهمية:
  chrome --use-fake-device-for-media-stream --use-fake-ui-for-media-stream --use-file-for-fake-video-capture=FILE.y4m
كل فيديو يمثل سيناريو حقيقياً واجهناه في التجارب الميدانية.
التشغيل: python tests/make_videos.py   (يكتب إلى tests/out/)
يحتاج: numpy, pillow
"""
import os, sys, math
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


def tamper():
    """العبث بالكاميرا: تغطية العدسة، أو توجيه الكاميرا لمكان آخر."""
    rng = np.random.default_rng(21); base, gone = _pair('gum_mouse_pair.png'); OW, OH = base.size
    g = np.asarray(gone).copy(); b = np.asarray(base); g[:, 190:] = b[:, 190:]; gum_gone = Image.fromarray(g)
    # 1) يد تغطي العدسة ~15 ث وتُؤخذ العلكة تحتها ثم تُرفع اليد — يُفترض: تنبيه «تغطية الكاميرا» + نقص العلكة (لا الماوس)
    def cover(img, k):  # k: 0..1 نسبة التغطية
        out = img.copy(); d = ImageDraw.Draw(out); r = int(60 + k * 900)
        d.ellipse([OW // 2 - r, OH // 2 - r, OW // 2 + r, OH // 2 + r], fill=(150, 105, 85))
        return out.filter(ImageFilter.GaussianBlur(6 if k >= 1 else 2))
    seq = [noisy(rng, base) for _ in range(24)] + [noisy(rng, cover(base, i / 4)) for i in range(1, 5)]
    seq += [noisy(rng, cover(gum_gone, 1), 3) for _ in range(60)] + [noisy(rng, gum_gone) for _ in range(100)]
    write_y4m('cover.y4m', seq)
    # 2) توجيه الكاميرا لمشهد آخر (رف مختلف) — يُفترض: تنبيه «تغيّر اتجاه الكاميرا» بلا حالات نقص
    rng = np.random.default_rng(22); other = _pair('shelf_focus_pair.png')[0].resize((OW, OH))
    mv = lambda img, dx: img.transform(img.size, Image.AFFINE, (1, 0, dx, 0, 1, 0), fillcolor=(30, 30, 40))
    seq = [noisy(rng, base) for _ in range(24)] + [noisy(rng, mv(base, 60 * i)) for i in range(1, 4)] + [noisy(rng, other) for _ in range(120)]
    write_y4m('turn.y4m', seq)


def relocate():
    """الموظف ينقل القطعة لرف تحته أو يدير زاويتها (تجربة ميدانية) — يُفترض: لا إنذار، بل حدث «نُقلت» معلوماتي."""
    base, gone = _pair('gum_mouse_pair.png'); b = np.asarray(base).astype(np.int16); g = np.asarray(gone).astype(np.int16)
    X0, Y0, X1, Y1 = 55, 125, 172, 238  # العلكة
    mask = ((b.max(2) - b.min(2)) > 55) | (b.sum(2) > 420); mask[:Y0] = 0; mask[Y1:] = 0; mask[:, :X0] = 0; mask[:, X1:] = 0  # ألوان العلكة (لا سطح اللابتوب الداكن)
    mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    item = base.crop((X0, Y0, X1, Y1)); m = Image.fromarray((mask[Y0:Y1, X0:X1] * 255).astype(np.uint8))
    empty = Image.fromarray(np.where(mask[..., None], g, b).astype(np.uint8))  # المكان بدون العلكة
    def put(bg, dx, dy, rot=0):
        out = bg.copy(); it, mm = (item.rotate(rot, resample=Image.BICUBIC, expand=True), m.rotate(rot, resample=Image.BICUBIC, expand=True)) if rot else (item, m)
        cx, cy = (X0 + X1) // 2 + dx, (Y0 + Y1) // 2 + dy; out.paste(it, (cx - it.size[0] // 2, cy - it.size[1] // 2), mm); return out
    hand = lambda im, x, y: (lambda c: (ImageDraw.Draw(c).ellipse([x, y, x + 130, y + 120], fill=(205, 160, 135)), c)[1])(im.copy())
    for name, dx, dy, rot, seed in [('move', 40, 165, 0, 31), ('rotate', 0, 0, 28, 32)]:
        rng = np.random.default_rng(seed); seq = [noisy(rng, base) for _ in range(24)]
        seq += [noisy(rng, hand(base, 60, 120)), noisy(rng, hand(empty, 70, 160)), noisy(rng, hand(put(empty, dx // 2, dy // 2, rot / 2), 80 + dx // 2, 140 + dy // 2))]
        seq += [noisy(rng, hand(put(empty, dx, dy, rot), 120 + dx, 150 + dy)), noisy(rng, hand(put(empty, dx, dy, rot), 200 + dx, 200 + dy))]
        seq += [noisy(rng, put(empty, dx, dy, rot)) for _ in range(120)]
        write_y4m(name + '.y4m', seq)
    # 3) حملها الموظف ~6 ث ثم وضعها على الرف تحته — يُفترض: لا إنذار (تُغلق حالة الشيل «نُقلت»)
    rng = np.random.default_rng(33); seq = [noisy(rng, base) for _ in range(24)] + [noisy(rng, hand(base, 60, 120)), noisy(rng, hand(empty, 70, 160))]
    seq += [noisy(rng, empty) for _ in range(24)] + [noisy(rng, hand(put(empty, 40, 165), 160, 320))] + [noisy(rng, put(empty, 40, 165)) for _ in range(120)]
    write_y4m('movelate.y4m', seq)
    # 4) سرقة العلكة مع وضع قطعة أخرى مختلفة (علبة زرقاء) في الأسفل — يُفترض: إنذار للعلكة رغم ظهور قطعة
    rng = np.random.default_rng(34)
    def box(im):
        out = im.copy(); d = ImageDraw.Draw(out); d.rectangle([110, 300, 200, 370], fill=(40, 90, 200)); d.rectangle([120, 312, 190, 330], fill=(230, 230, 240)); return out
    seq = [noisy(rng, base) for _ in range(24)] + [noisy(rng, hand(base, 60, 120)), noisy(rng, hand(empty, 70, 160)), noisy(rng, hand(box(empty), 160, 320))]
    seq += [noisy(rng, box(empty)) for _ in range(120)]
    write_y4m('stealadd.y4m', seq)


# ===================== رف بضاعة متكررة (شيبس، رافايلو) بكاميرا مائلة من الأعلى =====================
# كل صف فيه عدة قطع متطابقة خلف بعضها. عند أخذ القطعة الأمامية تظهر التي خلفها أعلى قليلاً وأصغر، ويظهر جزء من سطح الرف.
SW, SH = 640, 480
CHIPS = [(200, 30, 40), (30, 90, 190), (40, 150, 60), (230, 190, 30), (150, 40, 150)]
def shelf_img(counts, body=None, wrist=None, hand=None):
    rng = np.random.default_rng(99)  # خلفية ثابتة
    a = np.full((SH, SW, 3), (215, 205, 185), np.float32) + rng.normal(0, 6, (SH, SW, 1)); im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im)
    for tier, (lip, fh, fw) in enumerate([(220, 72, 58), (420, 118, 60)]):
        d.polygon([(10, lip - 70), (400, lip - 70), (410, lip), (0, lip)], fill=(170, 165, 160))  # سطح الرف
        for r in range(5):
            cx = 45 + r * 78; k = counts.get((tier, r), 4)
            for i in reversed(range(4 - k, 4)):  # من الخلف للأمام؛ الصف الناقص يبدأ من الخلف (القطع الأمامية أُخذت)
                sc = 1 - 0.05 * i; w, h = fw * sc, fh * sc; y1 = lip - 4 - i * 13; x0 = cx - w / 2
                if tier == 0:  # علب رافايلو: أبيض مع شريط ذهبي
                    d.rectangle([x0, y1 - h - 9 * sc, x0 + w, y1 - h], fill=(235, 235, 230)); d.rectangle([x0, y1 - h, x0 + w, y1], fill=(245, 245, 240), outline=(120, 110, 90))
                    d.rectangle([x0, y1 - h * .55, x0 + w, y1 - h * .4], fill=(200, 160, 40)); d.ellipse([cx - 9 * sc, y1 - h * .3, cx + 9 * sc, y1 - h * .1], fill=(190, 30, 40))
                else:  # أكياس شيبس ملونة مع شعار وتجعدات
                    col = CHIPS[r]; d.rounded_rectangle([x0, y1 - h, x0 + w, y1], radius=8 * sc, fill=col, outline=tuple(int(c * .6) for c in col))
                    d.ellipse([cx - 20 * sc, y1 - h * .7, cx + 20 * sc, y1 - h * .45], fill=(250, 245, 230)); d.rectangle([cx - 14 * sc, y1 - h * .3, cx + 14 * sc, y1 - h * .2], fill=(250, 220, 60))
                    for t in range(3): d.line([x0 + 6, y1 - h + 10 + t * 9 * sc, x0 + w - 6, y1 - h + 14 + t * 9 * sc], fill=tuple(min(255, int(c * 1.3) + 20) for c in col), width=2)
            d.rectangle([cx - 22, lip + 2, cx + 22, lip + 16], fill=(250, 250, 250)); d.line([cx - 16, lip + 9, cx + 12, lip + 9], fill=(40, 40, 40), width=2)  # بطاقة السعر
        d.rectangle([0, lip, 410, lip + 18], outline=(120, 115, 110))
    if body:  # علامات نقاط الجسم (للمحاكاة بدل MediaPipe Pose): أكتاف صفراء، ورك أزرق، معصم سماوي
        d.rectangle([450, 120, 610, 380], fill=(110, 110, 120))
        for p in [(470, 150), (590, 150)]: d.ellipse([p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8], fill=(255, 220, 0))
        for p in [(480, 300), (580, 300)]: d.ellipse([p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8], fill=(0, 80, 255))
    if hand: d.ellipse([hand[0] - 40, hand[1] - 35, hand[0] + 40, hand[1] + 35], fill=(205, 160, 135))
    if wrist: d.ellipse([wrist[0] - 9, wrist[1] - 9, wrist[0] + 9, wrist[1] + 9], fill=(0, 255, 255))
    return im

def stock():
    rng = np.random.default_rng(41); B = shelf_img({})
    # 1) سحب قطعة أمامية من صف شيبس، ثم علبة رافايلو — يُفترض: حدثا «التقاط»، بلا إنذار
    c1 = {(1, 1): 3}; c2 = {(1, 1): 3, (0, 3): 3}
    seq = [noisy(rng, B) for _ in range(24)] + [noisy(rng, shelf_img({}, hand=(123, 340))), noisy(rng, shelf_img(c1, hand=(123, 330))), noisy(rng, shelf_img(c1, hand=(150, 250)))]
    seq += [noisy(rng, shelf_img(c1)) for _ in range(28)] + [noisy(rng, shelf_img(c1, hand=(279, 170))), noisy(rng, shelf_img(c2, hand=(279, 160))), noisy(rng, shelf_img(c2, hand=(300, 90)))]
    seq += [noisy(rng, shelf_img(c2)) for _ in range(100)]
    write_y4m('stockpick.y4m', seq)
    # 2) تعبئة صف ناقص (الموظف يضيف قطعاً للأمام) — يُفترض: «تعبئة»، لا «التقاط»
    rng = np.random.default_rng(42); R = {(1, 2): 2}
    seq = [noisy(rng, shelf_img(R)) for _ in range(24)] + [noisy(rng, shelf_img(R, hand=(201, 340))), noisy(rng, shelf_img({}, hand=(201, 330))), noisy(rng, shelf_img({}, hand=(230, 250)))]
    seq += [noisy(rng, shelf_img({})) for _ in range(100)]
    write_y4m('restock.y4m', seq)
    # 2ب) سحب قطعة ثم إرجاعها لنفس الصف بعد ~5 ث (ترتيب أو فحص) — في وضع «لا بيع»: حالة تُغلق «رجعت» بلا إنذار
    rng = np.random.default_rng(44); c1 = {(1, 1): 3}
    seq = [noisy(rng, B) for _ in range(24)] + [noisy(rng, shelf_img({}, hand=(123, 340))), noisy(rng, shelf_img(c1, hand=(123, 330))), noisy(rng, shelf_img(c1, hand=(150, 250)))]
    seq += [noisy(rng, shelf_img(c1)) for _ in range(20)] + [noisy(rng, shelf_img(c1, hand=(123, 340))), noisy(rng, shelf_img({}, hand=(123, 330))), noisy(rng, shelf_img({}, hand=(150, 250)))]
    seq += [noisy(rng, B) for _ in range(100)]
    write_y4m('stockret.y4m', seq)
    # 2ج) تدوير كيس الشيبس الأمامي في مكانه (~12°) أو دفعه جانباً قليلاً (ترتيب الرف) — في وضع «لا بيع»: لا إنذار
    back = np.asarray(shelf_img({(1, 2): 3})).astype(np.int16)
    X0, Y0, X1, Y1 = 171, 298, 232, 417  # الكيس الأمامي للصف الثالث (cx=201، عرض 60، ارتفاع 118)
    bm = Image.new('L', (X1 - X0, Y1 - Y0), 0); ImageDraw.Draw(bm).rounded_rectangle([0, 0, X1 - X0 - 1, Y1 - Y0 - 1], radius=8, fill=255); bag = B.crop((X0, Y0, X1, Y1))
    def tweak(rot, dx):
        out = Image.fromarray(back.astype(np.uint8)); b2, m2 = bag.rotate(rot, resample=Image.BICUBIC, expand=True), bm.rotate(rot, resample=Image.BICUBIC, expand=True)
        out.paste(b2, ((X0 + X1) // 2 - b2.size[0] // 2 + dx, (Y0 + Y1) // 2 - b2.size[1] // 2), m2); return out
    for name, rot, dx, seed in [('stockturn', 12, 0, 45), ('stocknudge', 0, 10, 46)]:
        rng = np.random.default_rng(seed); T = tweak(rot, dx)
        handT = T.copy(); ImageDraw.Draw(handT).ellipse([161, 295, 241, 365], fill=(205, 160, 135))  # اليد فوق الكيس بعد تعديله
        seq = [noisy(rng, B) for _ in range(24)] + [noisy(rng, shelf_img({}, hand=(201, 340))), noisy(rng, handT), noisy(rng, T)]
        seq += [noisy(rng, T) for _ in range(120)]
        write_y4m(name + '.y4m', seq)
    # 3) رف ثابت مع تذبذب التعريض والضجيج — يُفترض: صفر أحداث
    rng = np.random.default_rng(43)
    write_y4m('stockidle.y4m', [noisy(rng, B, 4, 1 + 0.03 * np.sin(i / 5)) for i in range(140)])

def conceal():
    """إخفاء قطعة: اليد تلمس الرف ثم تذهب إلى منطقة الجيب/الخصر — يُفترض: «اشتباه إخفاء». والمقارنة: وضعها في السلة بعيداً عن الجسم."""
    for name, dest, seed in [('conceal', (485, 330), 51), ('basket', (430, 455), 52)]:
        rng = np.random.default_rng(seed); c = {(1, 3): 3}; idle = (600, 330)
        path = [idle] * 48 + [(520, 330), (400, 340), (279, 350)] + [(279, 345)] * 2 + [(400, 340), (dest[0] + 30, dest[1])] + [dest] * 10 + [idle] * 140
        seq = []
        for k, w in enumerate(path):
            taken = 51 <= k
            seq.append(noisy(rng, shelf_img(c if taken else {}, body=True, wrist=w, hand=(w[0] - 25, w[1] - 10) if 49 <= k < 53 else None)))
        write_y4m(name + '.y4m', seq)


# ===================== تتبّع الأيدي (تجربة ميدانية) =====================
# سطح خشبي مزخرف وموبايلات ملساء داكنة: أخذ الموبايل «يكشف» الزخرفة (يبدو إضافة)، ووضعه «يغطيها» (يبدو نقصاً).
# اليد: بيضاوي بلون الجلد مع علامة سماوية في وسطها (يقرؤها كاشف الأيدي الوهمي بدل MediaPipe).
def hand_scene(items, hand=None, marker=True, cloth=False):
    yy, xx = np.mgrid[0:SH, 0:SW].astype(np.float32)
    v = 150 + 22 * np.sin(xx / 7 + 3 * np.sin(yy / 31)) + 10 * np.sin(yy / 4.3)
    a = np.stack([v, v * .74, v * .52], 2)
    if cloth:  # النصف الأيمن قماش أزرق بخطوط مائلة (سطح مختلف عن الخشب)
        c = 110 + 35 * (np.sin((xx + yy) / 3.5) > 0); a[:, 320:] = np.stack([c * .35, c * .5, c * 1.2], 2)[:, 320:]
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im)
    for kind, cx, cy in items:
        if kind == 'phone': d.rounded_rectangle([cx - 38, cy - 70, cx + 38, cy + 70], radius=10, fill=(28, 28, 34), outline=(70, 70, 80), width=2); d.rectangle([cx - 30, cy - 58, cx + 30, cy + 52], fill=(36, 38, 46))
        elif kind == 'phoneR':  # نفس الموبايل بعد وضعه مائلاً قليلاً وبإضاءة مختلفة (لا يطابق بصمته الأولى تماماً)
            w, h, a = 38, 70, math.radians(14); pts = [(cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)) for x, y in [(-w, -h), (w, -h), (w, h), (-w, h)]]
            d.polygon(pts, fill=(48, 46, 54), outline=(95, 95, 105)); d.polygon([(cx + x * .8 * math.cos(a) - y * .82 * math.sin(a), cy + x * .8 * math.sin(a) + y * .82 * math.cos(a)) for x, y in [(-w, -h), (w, -h), (w, h), (-w, h)]], fill=(60, 64, 76))
        elif kind == 'box': d.rectangle([cx - 50, cy - 82, cx + 50, cy + 82], fill=(230, 40, 50)); [d.line([cx - 50, cy - 82 + k * 12, cx + 50, cy - 70 + k * 12], fill=(250, 230, 60), width=4) for k in range(14)]  # تغطي كل ما وراء الموبايل
        elif kind == 'plain': d.rectangle([cx - 40, cy - 60, cx + 40, cy + 60], fill=(45, 45, 50))  # علبة سادة بلا تفاصيل
        elif kind.startswith('back'):  # قطع خلفية مزدحمة (علب ملونة بخطوط) تُغطّى جزئياً بما يوضع أمامها
            col = [(220, 60, 60), (60, 150, 220), (240, 190, 40), (90, 180, 90)][int(kind[4:])]
            d.rectangle([cx - 46, cy - 90, cx + 46, cy + 90], fill=col); [d.line([cx - 46, cy - 90 + k * 14, cx + 46, cy - 80 + k * 14], fill=(250, 250, 250), width=3) for k in range(13)]
        elif kind == 'gift': d.rectangle([cx - 36, cy - 36, cx + 36, cy + 36], fill=(40, 90, 210)); d.rectangle([cx - 6, cy - 36, cx + 6, cy + 36], fill=(250, 250, 250)); d.rectangle([cx - 36, cy - 6, cx + 36, cy + 6], fill=(250, 250, 250))
    if hand:
        d.ellipse([hand[0] - 45, hand[1] - 40, hand[0] + 45, hand[1] + 40], fill=(205, 160, 135)); d.rectangle([hand[0] - 30, min(SH, hand[1] + 30), hand[0] + 30, SH], fill=(60, 64, 80))  # الذراع حتى أسفل الصورة
        if marker: d.ellipse([hand[0] - 9, hand[1] - 9, hand[0] + 9, hand[1] + 9], fill=(0, 255, 255))
    return im

def hands():
    A, B = (180, 240), (460, 250)
    def run(name, before, after_take, after_put, put_at, seed, marker=True, cloth=False):
        rng = np.random.default_rng(seed); f = lambda it, h=None: noisy(rng, hand_scene(it, h, marker, cloth), 3)
        seq = [f(before) for _ in range(24)]
        seq += [f(before, (A[0], A[1] + 120)), f(before, (A[0], A[1] + 20)), f(before, A), f(after_take, A), f(after_take, A)]  # اليد تمسك القطعة
        if put_at:  # تحملها وتضعها في مكان آخر
            seq += [f(after_take, (A[0] + 90, A[1] - 10)), f(after_take, (B[0] - 90, B[1] - 10))] + [f(after_put, B) for _ in range(3)] + [f(after_put, (B[0], B[1] + 120)), f(after_put, (B[0], B[1] + 260))]
        else:       # تخرج بها من الصورة
            seq += [f(after_take, (A[0], A[1] + 120)), f(after_take, (A[0], A[1] + 260))]
        seq += [f(after_put if put_at else after_take) for _ in range(170)]
        write_y4m(name + '.y4m', seq)
    ph, ph2 = [('phone', *A)], [('phone', *B)]
    run('handmove', ph, [], ph2, B, 61)                                   # نقل الموبايل من عارضة لأخرى — يُفترض: نقل بلا إنذار
    run('movenohand', ph, [], ph2, B, 62, marker=False)                   # نفس النقل بدون ذكاء اصطناعي — يُفترض: نقل بلا إنذار
    run('handtake', ph, [], None, None, 63)                               # أخذ الموبايل عن السطح المزخرف — يُفترض: شيل ثم إنذار
    run('reveal', [('box', *A), ('phone', *A)], [('box', *A)], None, None, 64)  # أخذ قطعة يكشف ما وراءها — يُفترض: شيل ثم إنذار
    run('handswap', ph, [], [('gift', *B)], B, 65)
    run('handmove2', [('plain', *A)], [], [('plain', *B)], B, 66, cloth=True)
    # (تجربة ميدانية) «غيّرت مكان قطعة 2 سم فحسبها سرقة»: الموبايل يُزاح قليلاً في مكانه (بيد وبدونها)
    def nudge(name, dx, seed, marker):
        rng = np.random.default_rng(seed); f = lambda it, h=None: noisy(rng, hand_scene(it, h, marker), 3); P0, P1 = [('phone', *A)], [('phone', A[0] + dx, A[1] + 4)]
        seq = [f(P0) for _ in range(24)] + [f(P0, (A[0], A[1] + 120)), f(P0, A), f(P1, (A[0] + dx, A[1])), f(P1, (A[0] + dx, A[1] + 140)), f(P1, (A[0] + dx, A[1] + 280))] + [f(P1) for _ in range(170)]
        write_y4m(name + '.y4m', seq)
    nudge('nudgeitem', 22, 68, True); nudge('nudgeitem_nohand', 22, 69, False); nudge('nudgeitem2', 50, 70, True)  # علبة سادة من الخشب إلى قماش أزرق — يُفترض: نقل بلا إنذار
    # يد تضع علبة جديدة على اليسار ثم تأخذ الموبايل من اليمين — يُفترض: إنذار للموبايل، و«إضافة» للعلبة، بلا نقل
    rng = np.random.default_rng(67); f = lambda it, h=None: noisy(rng, hand_scene(it, h), 3); g, p2 = ('gift', *A), ('phone', *B)
    seq = [f([p2]) for _ in range(24)] + [f([p2], (A[0], A[1] + 120)), f([p2], A), f([g, p2], A), f([g, p2], A), f([g, p2], (A[0] + 100, A[1] + 20))]
    seq += [f([g, p2], (B[0] - 80, B[1] + 10)), f([g, p2], B), f([g], B), f([g], B), f([g], (B[0], B[1] + 120)), f([g], (B[0], B[1] + 260))] + [f([g]) for _ in range(170)]
    write_y4m('putthentake.y4m', seq)
    # (تجربة ميدانية) «أضفت قطعة اعتبرها سرقة لأنها غطّت جزءاً مما خلفها» و«نقلت قطعة فاعتبرها سرقتين»
    back = [('back0', 110, 220), ('back1', 250, 220), ('back2', 390, 220), ('back3', 530, 220)]
    def clutter(name, seed, before, after, touch, marker=True):
        rng = np.random.default_rng(seed); f = lambda it, h=None: noisy(rng, hand_scene(back + it, h, marker), 3)
        seq = [f(before) for _ in range(24)]
        for k, (pt, state) in enumerate(touch): seq += [f(state, pt)] * 3
        seq += [f(after, (touch[-1][0][0], touch[-1][0][1] + 150)), f(after, (touch[-1][0][0], touch[-1][0][1] + 280))] + [f(after) for _ in range(170)]
        write_y4m(name + '.y4m', seq)
    G = ('gift', 250, 300)  # علبة زرقاء توضع أمام العلبة الثانية فتغطي جزءها السفلي
    for mk, sfx in [(True, ''), (False, '_nohand')]:
        clutter('addfront' + sfx, 71, [], [G], [((250, 300), [G])], mk)
        P0, P1 = ('phone', 110, 300), ('phone', 530, 300)  # موبايل أمام العلبة الأولى يُنقل أمام الرابعة
        clutter('moveclutter' + sfx, 72, [P0], [P1], [((110, 300), [P0]), ((110, 300), []), ((320, 300), []), ((530, 300), [P1])], mk)
        # الحالة الأصعب: موبايل أسود أملس يوضع أمام علبة مخططة (يغطي زخرفتها)، ونقل موبايل يُوضع مائلاً بإضاءة مختلفة
        Pf = ('phone', 250, 290)
        clutter('addfront2' + sfx, 73, [], [Pf], [((250, 290), [Pf])], mk)
        Q0, Q1 = ('phone', 110, 290), ('phoneR', 530, 290)
        clutter('moveclutter2' + sfx, 74, [Q0], [Q1], [((110, 290), [Q0]), ((110, 290), []), ((320, 300), []), ((530, 290), [Q1])], mk)
                        # أخذ الموبايل ووضع علبة مختلفة — يُفترض: إنذار للموبايل


# ===================== «تتبّع ما تحمله اليد» على عارضة بيضاء (تجربة ميدانية) =====================
# «سرقت قطعة حقيقةً ولم ينبهني، ولما رجعتها نبهني»: علب بيضاء بطباعة زرقاء على رف أبيض — الملمس يقلب الاتجاه.
def white_scene(items, hand=None, held=None, marker=True):
    im = Image.new('RGB', (SW, SH), (236, 238, 242)); d = ImageDraw.Draw(im)
    d.rectangle([0, 330, SW, 345], fill=(220, 222, 228))  # حافة الرف
    def box(cx, cy, col):
        d.rectangle([cx - 42, cy - 70, cx + 42, cy + 70], fill=(248, 248, 250), outline=(200, 205, 215), width=2)
        d.rectangle([cx - 42, cy - 70, cx + 42, cy - 48], fill=col); d.ellipse([cx - 22, cy - 25, cx + 22, cy + 19], fill=(60, 70, 90)); d.rectangle([cx - 30, cy + 35, cx + 30, cy + 45], fill=col)
    for cx, col in items: box(cx, 260, col)
    if hand:
        if held: box(hand[0], hand[1] - 10, held)  # القطعة في اليد
        d.ellipse([hand[0] - 40, hand[1] - 20, hand[0] + 40, hand[1] + 50], fill=(205, 160, 135)); d.rectangle([hand[0] - 28, min(SH, hand[1] + 40), hand[0] + 28, SH], fill=(60, 64, 80))
        if marker: d.ellipse([hand[0] - 8, hand[1] + 7, hand[0] + 8, hand[1] + 23], fill=(0, 255, 255))
    return im

def carry():
    B = (30, 110, 220); R = (220, 60, 60); G = (40, 160, 90)
    shelf = [(130, B), (240, R), (350, B), (460, G)]
    def run(name, seed, before, after, path):  # path: [(نقطة اليد، اللون المحمول أو None)]
        rng = np.random.default_rng(seed); f = lambda it, h=None, c=None: noisy(rng, white_scene(it, h, c), 3)
        seq = [f(before) for _ in range(24)]
        for k, (pt, col, scene) in enumerate(path): seq += [f(scene, pt, col)] * 2
        seq += [f(after) for _ in range(150)]
        write_y4m(name + '.y4m', seq)
    nored = [s_ for s_ in shelf if s_[1] != R]
    # سرقة: اليد تدخل فارغة، تأخذ العلبة الحمراء، وتخرج بها من الأسفل
    run('carrytake', 81, shelf, nored, [((240, 470), None, shelf), ((240, 330), None, shelf), ((240, 300), R, nored), ((240, 420), R, nored), ((240, 520), R, nored)])
    # إرجاع: اليد تدخل بالعلبة الحمراء وتضعها وتخرج فارغة (يبدأ الفيديو بعد السرقة)
    run('carryback', 82, nored, shelf, [((240, 520), R, nored), ((240, 400), R, nored), ((240, 330), None, shelf), ((240, 470), None, shelf)])
    # إضافة: علبة خضراء جديدة توضع في مكان فارغ
    newg = shelf + [(560, G)]
    run('carryadd', 83, shelf, newg, [((560, 520), G, shelf), ((560, 400), G, shelf), ((560, 330), None, newg), ((560, 470), None, newg)])


if __name__ == '__main__':
    live(); gum(); user(); focus(); steal(); tamper(); relocate(); stock(); conceal(); hands(); carry()
