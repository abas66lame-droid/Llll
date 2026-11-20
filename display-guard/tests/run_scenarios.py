# -*- coding: utf-8 -*-
"""
اختبارات شاملة (end-to-end) لـ haris.html على Chrome بكاميرا وهمية.
  1) python tests/make_videos.py
  2) python tests/run_scenarios.py            (كل السيناريوهات)
     python tests/run_scenarios.py focus gum  (سيناريوهات محددة)
يحتاج: pip install playwright && playwright install chromium   (أو ضع مسار Chrome في متغير CHROME)
كل سيناريو يستغرق 30-60 ثانية لأنه يعمل بالزمن الحقيقي (مهلة الاختبار 10 ثوانٍ).
"""
import asyncio, os, sys, time
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = 'file://' + os.path.abspath(os.path.join(HERE, '..', 'haris.html'))
OUT = os.path.join(HERE, 'out')
CHROME = os.environ.get('CHROME')  # مثال: /usr/bin/google-chrome

GUM = {'id': 'gum', 'name': 'العلكة', 'section': '', 'x': 0.1672, 'y': 0.1796, 'w': 0.4554, 'h': 0.2764}
MOUSE = {'id': 'mouse', 'name': 'الماوس', 'section': '', 'x': 0.7166, 'y': 0.2577, 'w': 0.2492, 'h': 0.2233}
# كاشف أشخاص وهمي (يحاكي MediaPipe): يعتبر البكسلات الخضراء (كمّ الذراع) شخصاً
MOCK_PERSON = r"""(()=>{MP.state='ready';MP.hand=null;
 MP.obj={detect:c=>{const x=c.getContext('2d').getImageData(0,0,c.width,c.height).data,W=c.width,H=c.height;let l=1e9,t=1e9,r=-1,b=-1,n=0;
  for(let y=0;y<H;y+=3)for(let xx=0;xx<W;xx+=3){const i=(y*W+xx)*4;if(x[i+1]>110&&x[i+1]-x[i]>60&&x[i+1]-x[i+2]>35){n++;l=Math.min(l,xx);r=Math.max(r,xx);t=Math.min(t,y);b=Math.max(b,y);}}
  return {detections:n>30?[{boundingBox:{originX:l,originY:t,width:r-l,height:b-t},categories:[{categoryName:'person',score:.9}]}]:[]};}};})();"""

# لا حالة نقص مفتوحة أو منبَّه عليها (النقل أو التدوير ليس شيلاً)
NO_ALARM = lambda ev: not [1 for _, k, st in ev if k in ('removal', 'night') and st in ('pending', 'incident')]

# (اسم، فيديو، مناطق، مدة بالثواني، دالة تحقق على قائمة [اسم_المنطقة، النوع، الحالة]، كاشف وهمي)
SCENARIOS = {
    'live':  ('live.y4m',  [{'id': 'z1', 'name': 'عارضة', 'section': '', 'x': .03, 'y': .07, 'w': .47, 'h': .38}], 45,
              lambda ev: any(s in ('incident', 'resolved') for _, k, s in ev if k == 'removal'), None),
    'gum':   ('gum.y4m',   [{'id': 'g', 'name': 'علكة', 'section': '', 'x': .35, 'y': .35, 'w': .3, 'h': .3}], 25,
              lambda ev: [s for _, k, s in ev if k == 'removal'] == ['incident'], None),
    'user':  ('user.y4m',  [GUM, MOUSE], 40,  # 40ث: يتسع لأجهزة أبطأ (MediaPipe على CPU يبطئ القراءات)
              lambda ev: {z for z, k, s in ev if k == 'removal' and s == 'incident'} == {'العلكة', 'الماوس'}, None),
    'focus': ('focus.y4m', [{'id': 'k', 'name': 'ك', 'section': '', 'x': .149, 'y': .27, 'w': .52, 'h': .17}], 40,
              lambda ev: not [1 for _, k, _ in ev if k == 'removal'], None),
    'arm':   ('arm.y4m',   [GUM], 40, lambda ev: not [1 for _, k, _ in ev if k == 'removal'], MOCK_PERSON),
    'nudge': ('nudge.y4m', [GUM, MOUSE], 32,
              lambda ev: {z for z, k, _ in ev if k == 'removal'} == {'العلكة'}, None),
    'nudge2': ('nudge2.y4m', [GUM, MOUSE], 20, lambda ev: not [1 for _, k, _ in ev if k == 'removal'], None),
    # السرقة لا تُخفى داخل «حركة الكاميرا»: ذراع تملأ الصورة، أو دفع الموبايل مع الأخذ
    'reach': ('reach.y4m', [GUM, MOUSE], 32, lambda ev: {z for z, k, _ in ev if k == 'removal'} == {'العلكة'}, None),
    'bumpsteal': ('bumpsteal.y4m', [GUM, MOUSE], 32, lambda ev: {z for z, k, _ in ev if k == 'removal'} == {'العلكة'}, None),
    # العبث بالكاميرا: تغطية العدسة مع أخذ قطعة تحتها، أو توجيهها لمكان آخر
    'cover': ('cover.y4m', [GUM, MOUSE], 44, lambda ev: any(k == 'tamper' for _, k, _ in ev) and {z for z, k, _ in ev if k == 'removal'} == {'العلكة'}, None),
    # نقل القطعة لرف تحته (نفس العارضة، أو من عارضة لأخرى) أو إدارة زاويتها: لا إنذار
    'move': ('move.y4m', [{'id': 'all', 'name': 'الستاند', 'section': '', 'x': .08, 'y': .2, 'w': .62, 'h': .65}], 32, NO_ALARM, None),
    'move2': ('move.y4m', [{'id': 'up', 'name': 'الرف العلوي', 'section': '', 'x': .1, 'y': .2, 'w': .45, 'h': .33}, {'id': 'dn', 'name': 'الرف السفلي', 'section': '', 'x': .1, 'y': .56, 'w': .55, 'h': .3}], 32, NO_ALARM, None),
    'rotate': ('rotate.y4m', [GUM, MOUSE], 32, NO_ALARM, None),
    'movelate': ('movelate.y4m', [{'id': 'up', 'name': 'الرف العلوي', 'section': '', 'x': .1, 'y': .2, 'w': .45, 'h': .33}, {'id': 'dn', 'name': 'الرف السفلي', 'section': '', 'x': .1, 'y': .56, 'w': .55, 'h': .3}], 36, NO_ALARM, None),
    # النقل لا يُخفي السرقة: أُخذت العلكة ووُضعت قطعة مختلفة في الأسفل — يجب أن يبقى الإنذار
    'stealadd': ('stealadd.y4m', [{'id': 'all', 'name': 'الستاند', 'section': '', 'x': .08, 'y': .2, 'w': .62, 'h': .65}], 32, lambda ev: [s for _, k, s in ev if k == 'removal'] == ['incident'] and not [1 for _, k, _ in ev if k == 'moved'], None),
    'turn': ('turn.y4m', [GUM, MOUSE], 28, lambda ev: any(k == 'tamper' for _, k, _ in ev) and not [1 for _, k, _ in ev if k == 'removal'], None),
}


async def run_one(p, name):
    vid, zones, secs, check, mock = SCENARIOS[name]
    args = ['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--use-file-for-fake-video-capture=' + os.path.join(OUT, vid)]
    b = await p.chromium.launch(executable_path=CHROME, args=args) if CHROME else await p.chromium.launch(args=args)
    pg = await (await b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)).new_page()
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    await pg.goto(HTML); await pg.wait_for_timeout(600)
    import json
    await pg.evaluate("z => { S.zones = z; S.cfg.test = true; S.cfg.testSec = 10; saveZones(); saveCfg(); }", zones)
    await pg.click('text=تشغيل الكاميرا')
    if mock:
        for _ in range(20):
            await pg.wait_for_timeout(300)
            if await pg.evaluate('MP.state') in ('error', 'ready'): break
        await pg.evaluate(mock)
    await pg.wait_for_timeout(secs * 1000)
    ev = await pg.evaluate("S.events.map(e => [zoneOf(e.zone).name, e.kind, e.status])")
    await b.close()
    ok = check(ev) and not errs
    print(('PASS' if ok else 'FAIL'), name, ev, errs if errs else '')
    return ok


async def main():
    names = sys.argv[1:] or list(SCENARIOS)
    async with async_playwright() as p:
        res = [await run_one(p, n) for n in names]
    print('%d/%d passed' % (sum(res), len(res)))
    sys.exit(0 if all(res) else 1)

asyncio.run(main())
