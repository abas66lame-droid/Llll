# -*- coding: utf-8 -*-
"""
كاميرات افتراضية للتجربة بدون أي ربط.
ترسم عارضة فيها أجهزة على رفّين، وتنفّذ سيناريو متكرر:
  - زبون يمر أمام الكاميرا (يجب ألا يسبب تنبيهاً)
  - منتج يُشال للعرض ويرجع خلال المهلة (لا تنبيه)
  - منتج يُباع ويُسجَّل بيعه (يُغلق كمُباع)
  - تنظيف: منتجان يُشالان ويرجعان بعد مدة أطول من المهلة (لا تنبيه لأن التنظيف مسجّل)
  - منتج يختفي بدون بيع (تنبيه: اختفاء غير مبرر) ثم يُعوَّض لاحقاً
"""
import random
import time
import numpy as np
from PIL import Image, ImageDraw

W, H = 1280, 720
COLORS = [(25, 25, 30), (190, 40, 45), (40, 90, 175), (235, 235, 235), (55, 140, 80), (160, 125, 40),
          (120, 45, 140), (210, 120, 30), (70, 70, 80), (30, 120, 140), (200, 60, 120), (100, 150, 60)]
SLOTS = [(70 + c * 200, 70 + r * 320) for r in range(2) for c in range(6)]   # 12 منتجاً
PW, PH = 150, 230

# مناطق العارضة الافتراضية (نسب من الصورة): كل رف مقسوم إلى نصفين
DEMO_ZONES = [
    {'name': 'رف علوي - يمين', 'section': 'الهواتف', 'x': 40 / W, 'y': 50 / H, 'w': 600 / W, 'h': 270 / H},
    {'name': 'رف علوي - يسار', 'section': 'الهواتف', 'x': 640 / W, 'y': 50 / H, 'w': 600 / W, 'h': 270 / H},
    {'name': 'رف سفلي - يمين', 'section': 'الحاسبات', 'x': 40 / W, 'y': 370 / H, 'w': 600 / W, 'h': 270 / H},
    {'name': 'رف سفلي - يسار', 'section': 'الحاسبات', 'x': 640 / W, 'y': 370 / H, 'w': 600 / W, 'h': 270 / H},
]


def zone_of_slot(i):
    x, y = SLOTS[i]
    return (0 if x < 640 else 1) + (0 if y < 300 else 2)


class DemoScene:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.present = [True] * 12
        self.variant = list(range(12))
        self.person = None   # (x, دخل منذ)
        self.bg = self._background()

    def _background(self):
        im = Image.new('RGB', (W, H), (205, 202, 195))
        d = ImageDraw.Draw(im)
        for y in (310, 630):
            d.rectangle([0, y, W, y + 22], fill=(115, 100, 85))
        d.rectangle([0, 0, W, 30], fill=(60, 60, 70))
        return im

    def _product(self, d, x, y, k):
        col = COLORS[k % len(COLORS)]
        d.rounded_rectangle([x, y, x + PW, y + PH], 16, fill=col, outline=(10, 10, 10), width=5)
        d.rectangle([x + 18, y + 18, x + PW - 18, y + 130], fill=(80 + k * 13 % 120, 150, 200 - k * 11 % 120))
        tc = (0, 0, 0) if sum(col) > 500 else (255, 255, 255)
        for j in range(5):
            d.text((x + 22, y + 140 + j * 16), 'MODEL-%02d  %d' % (k, 2026), fill=tc)

    def render(self):
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        for i, (x, y) in enumerate(SLOTS):
            if self.present[i]:
                self._product(d, x, y, self.variant[i])
        if self.person is not None:
            px = self.person
            d.ellipse([px, 120, px + 140, 260], fill=(90, 70, 60))
            d.rounded_rectangle([px - 40, 250, px + 180, H], 40, fill=(40, 60, 110))
        a = np.asarray(im, dtype=np.float32)
        a = a * self.rng.uniform(0.97, 1.03) + np.random.normal(0, 2.5, a.shape)
        dx, dy = self.rng.randint(-1, 1), self.rng.randint(-1, 1)
        a = np.roll(np.roll(a, dx, 1), dy, 0)
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


class DemoDirector:
    """يحرّك المشاهد حسب جدول زمني. post_sale/post_cleaning دوال يوفرها النظام."""

    def __init__(self, scene, cam_id, grace, post_sale, post_cleaning, offset=0):
        self.s = scene; self.cam = cam_id; self.g = grace
        self.post_sale = post_sale; self.post_cleaning = post_cleaning
        self.t0 = time.time() + offset
        self.done = set()
        self.cycle = 0

    def step(self):
        g = self.g
        t = time.time() - self.t0
        L = 10 * g + 40            # طول الدورة
        if t > L:
            self.t0 += L; self.cycle += 1; self.done = set(); t = time.time() - self.t0
            self.s.present = [True] * 12
        c = self.cycle
        a = (c * 5) % 12; b = (a + 3) % 12; cc = (a + 7) % 12; d1 = (a + 1) % 12; d2 = (a + 8) % 12
        plan = [
            (5, 'person_in', None), (9, 'person_out', None),
            (12, 'remove', a), (12 + 0.5 * g, 'return', a),                       # عرض لزبون ورجوع
            (2 * g, 'remove', b), (2 * g + 6, 'sale', b),                         # بيع
            (3.5 * g, 'clean', d1), (3.5 * g + 3, 'remove', d1), (3.5 * g + 4, 'remove', d2),
            (3.5 * g + 1.5 * g, 'return', d1), (3.5 * g + 1.6 * g, 'return', d2),  # تنظيف أطول من المهلة
            (6.5 * g, 'remove', cc), (8.5 * g, 'return', cc),                      # اختفاء غير مبرر ثم تعويض
            (8.5 * g + 6, 'return', b),                                            # تعويض المنتج المباع
        ]
        for i, (at, act, k) in enumerate(plan):
            if t >= at and i not in self.done:
                self.done.add(i)
                if act == 'person_in': self.s.person = 900
                elif act == 'person_out': self.s.person = None
                elif act == 'remove': self.s.present[k] = False
                elif act == 'return': self.s.present[k] = True
                elif act == 'sale': self.post_sale(self.cam, zone_of_slot(k), 1)
                elif act == 'clean': self.post_cleaning(self.cam, zone_of_slot(k)); self.post_cleaning(self.cam, zone_of_slot(d2))
        if self.s.person is not None:
            self.s.person = 900 - int((t - 5) * 120) % 700


class DemoSource:
    def __init__(self, seed):
        self.scene = DemoScene(seed)
        self.director = None

    def fetch(self):
        if self.director:
            self.director.step()
        return self.scene.render()
