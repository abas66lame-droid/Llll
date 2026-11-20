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


if __name__ == '__main__':
    live(); gum(); user(); focus(); steal(); tamper(); relocate(); stock(); conceal()
