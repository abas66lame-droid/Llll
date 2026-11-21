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
ZL = {'id': 'zl', 'name': 'عارضة يسار', 'section': '', 'x': 0.08, 'y': 0.2, 'w': 0.38, 'h': 0.6}
ZR = {'id': 'zr', 'name': 'عارضة يمين', 'section': '', 'x': 0.54, 'y': 0.2, 'w': 0.38, 'h': 0.6}
ZALL = {'id': 'za', 'name': 'العارضة', 'section': '', 'x': 0.05, 'y': 0.15, 'w': 0.9, 'h': 0.75}
SHELF = {'id': 'sh', 'name': 'رف الشيبس والشوكولا', 'section': 'مواد غذائية', 'mode': 'stock', 'x': 0.0, 'y': 0.17, 'w': 0.66, 'h': 0.75}
MOUSE = {'id': 'mouse', 'name': 'الماوس', 'section': '', 'x': 0.7166, 'y': 0.2577, 'w': 0.2492, 'h': 0.2233}
# كاشف أشخاص وهمي (يحاكي MediaPipe): يعتبر البكسلات الخضراء (كمّ الذراع) شخصاً
MOCK_PERSON = r"""(()=>{MP.state='ready';MP.hand=null;
 MP.obj={detect:c=>{const x=c.getContext('2d').getImageData(0,0,c.width,c.height).data,W=c.width,H=c.height;let l=1e9,t=1e9,r=-1,b=-1,n=0;
  for(let y=0;y<H;y+=3)for(let xx=0;xx<W;xx+=3){const i=(y*W+xx)*4;if(x[i+1]>110&&x[i+1]-x[i]>60&&x[i+1]-x[i+2]>35){n++;l=Math.min(l,xx);r=Math.max(r,xx);t=Math.min(t,y);b=Math.max(b,y);}}
  return {detections:n>30?[{boundingBox:{originX:l,originY:t,width:r-l,height:b-t},categories:[{categoryName:'person',score:.9}]}]:[]};}};})();"""

# كاشف وضعية الجسم وهمي (يحاكي MediaPipe Pose): يقرأ علامات ملونة (الأكتاف والورك يميناً بجانب الرف) — أكتاف صفراء، ورك أزرق، معصم سماوي
MOCK_POSE = r"""(()=>{MP.state='ready';MP.hand=null;MP.obj={detect:()=>({detections:[]})};S.cfg.conceal=true;
 const find=(c,f,x0=0)=>{const x=c.getContext('2d').getImageData(0,0,c.width,c.height).data,W=c.width,H=c.height,P=[];
  for(let y=0;y<H;y+=2)for(let xx=Math.floor(x0*W);xx<W;xx+=2){const i=(y*W+xx)*4;if(f(x[i],x[i+1],x[i+2]))P.push([xx/W,y/H]);}
  if(!P.length)return [];P.sort((a,b)=>a[0]-b[0]);const g=[[P[0]]];for(const p of P.slice(1)){const L=g[g.length-1],q=L[L.length-1];if(p[0]-q[0]>0.03)g.push([p]);else L.push(p);}
  return g.filter(a=>a.length>3).map(a=>({x:a.reduce((s,p)=>s+p[0],0)/a.length,y:a.reduce((s,p)=>s+p[1],0)/a.length}));};
 MP.pose={detect:c=>{const Y=find(c,(r,g,b)=>r>200&&g>180&&b<90,0.68),B=find(c,(r,g,b)=>b>200&&r<70&&g<130,0.68),R=find(c,(r,g,b)=>r<70&&g>200&&b>200);
  if(Y.length<2||B.length<2)return {landmarks:[]};const lm=Array.from({length:33},()=>({x:0,y:0,visibility:0}));
  lm[11]=Object.assign(Y[0],{visibility:1});lm[12]=Object.assign(Y[1],{visibility:1});lm[23]=Object.assign(B[0],{visibility:1});lm[24]=Object.assign(B[1],{visibility:1});
  if(R.length)lm[15]=Object.assign(R[0],{visibility:1});return {landmarks:[lm]};}};})();"""

# نقل واحد فقط من العارضة اليسرى (المصدر)، بلا أي حالة نقص مفتوحة
ONE_MOVE = lambda ev: [(z, k if k == 'moved' else s) for z, k, s in ev if k == 'moved' or s == 'moved'] == [('عارضة يسار', 'moved')] and NO_ALARM(ev)

# كاشف أيادٍ وهمي (يحاكي MediaPipe GestureRecognizer): العلامة السماوية وسط اليد = يد، بلا أشخاص
MOCK_HAND = r"""(()=>{MP.state='ready';MP.obj={detect:()=>({detections:[]})};
 MP.hand={recognize:c=>{const x=c.getContext('2d').getImageData(0,0,c.width,c.height).data,W=c.width,H=c.height;let sx=0,sy=0,n=0;
  for(let y=0;y<H;y+=2)for(let xx=0;xx<W;xx+=2){const i=(y*W+xx)*4;if(x[i]<70&&x[i+1]>200&&x[i+2]>200){sx+=xx;sy+=y;n++;}}
  if(n<4)return {landmarks:[]};const cx=sx/n/W,cy=sy/n/H;return {landmarks:[[[-.05,-.05],[.05,-.05],[.05,.05],[-.05,.05],[0,0]].map(([a,b])=>({x:cx+a,y:cy+b}))]};}};})();"""

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
    # رف بضاعة متكررة (شيبس، رافايلو) مع وجود بيع (noSales=False): سحب القطعة الأمامية = «التقاط»، والتعبئة = «تعبئة»، والثبات = لا شيء
    'stockpick': ('stockpick.y4m', [SHELF], 34, lambda ev: [k for _, k, _ in ev if k in ('pick', 'restock')] == ['pick', 'pick'] and NO_ALARM(ev), None, {'noSales': False}),
    'restock': ('restock.y4m', [SHELF], 26, lambda ev: [k for _, k, _ in ev if k in ('pick', 'restock')] == ['restock'] and NO_ALARM(ev), None, {'noSales': False}),
    'stockidle': ('stockidle.y4m', [SHELF], 30, lambda ev: not ev, None, {'noSales': False}),
    # وضع «لا يوجد بيع حالياً»: كل التقاط = حالة شيل بمهلة؛ لم ترجع = تنبيه سرقة، رجعت لنفس الصف = تُغلق بلا إنذار
    'stocksteal': ('stockpick.y4m', [SHELF], 34, lambda ev: [s for _, k, s in ev if k == 'removal'] == ['incident', 'incident'], None, {'noSales': True}),
    # تدوير كيس في مكانه أو دفعه جانباً قليلاً (ترتيب الرف) في وضع «لا بيع»: لا حالة شيل ولا إنذار
    'stockturn': ('stockturn.y4m', [SHELF], 30, NO_ALARM, None, {'noSales': True}),
    'stocknudge': ('stocknudge.y4m', [SHELF], 30, NO_ALARM, None, {'noSales': True}),
    'stockret': ('stockret.y4m', [SHELF], 30, lambda ev: [s for _, k, s in ev if k == 'removal'] == ['returned'], None, {'noSales': True}),
    # إخفاء قطعة في الجيب بعد لمس الرف = «اشتباه إخفاء»؛ وضعها في السلة بعيداً عن الجسم = لا اشتباه
    'conceal': ('conceal.y4m', [SHELF], 36, lambda ev: [k for _, k, _ in ev if k == 'conceal'] == ['conceal'], MOCK_POSE, {'noSales': False}),
    'basket': ('basket.y4m', [SHELF], 36, lambda ev: not [1 for _, k, _ in ev if k == 'conceal'], MOCK_POSE, {'noSales': False}),
    # تتبّع الأيدي: الترتيب حسب اليد لا حسب الملمس (موبايل أملس على سطح مزخرف، أو قطعة تكشف ما وراءها)
    'handmove': ('handmove.y4m', [ZL, ZR], 34, ONE_MOVE, MOCK_HAND),
    'handmove2': ('handmove2.y4m', [ZL, ZR], 34, ONE_MOVE, MOCK_HAND),
    'movenohand': ('movenohand.y4m', [ZL, ZR], 34, ONE_MOVE, None, {'ai': False}),
    'handtake': ('handtake.y4m', [ZL, ZR], 30, lambda ev: [(z, s) for z, k, s in ev if k == 'removal'] == [('عارضة يسار', 'incident')], MOCK_HAND),
    'reveal': ('reveal.y4m', [ZL, ZR], 30, lambda ev: [(z, s) for z, k, s in ev if k == 'removal'] == [('عارضة يسار', 'incident')], MOCK_HAND),
    'handswap': ('handswap.y4m', [ZL, ZR], 34, lambda ev: [(z, s) for z, k, s in ev if k == 'removal'] == [('عارضة يسار', 'incident')] and not [1 for _, k, s in ev if k == 'moved' or s == 'moved'], MOCK_HAND),
    'putthentake': ('putthentake.y4m', [ZL, ZR], 34, lambda ev: [(z, s) for z, k, s in ev if k == 'removal'] == [('عارضة يمين', 'incident')] and not [1 for _, k, s in ev if k == 'moved' or s == 'moved'], MOCK_HAND),
    # عارضة مزدحمة: إضافة قطعة تغطي جزءاً مما خلفها ≠ سرقة، ونقل قطعة = نقل واحد لا سرقتان (بيد وبدونها)
    'addfront': ('addfront.y4m', [ZALL], 32, lambda ev: NO_ALARM(ev) and [k for _, k, _ in ev] == ['added'], MOCK_HAND),
    'addfront_nohand': ('addfront_nohand.y4m', [ZALL], 32, NO_ALARM, None, {'ai': False}),
    'moveclutter': ('moveclutter.y4m', [ZALL], 36, lambda ev: NO_ALARM(ev) and len([1 for _, k, s in ev if k == 'moved' or s == 'moved']) == 1, MOCK_HAND),
    'moveclutter_nohand': ('moveclutter_nohand.y4m', [ZALL], 36, lambda ev: NO_ALARM(ev) and len([1 for _, k, s in ev if k == 'moved' or s == 'moved']) == 1, None, {'ai': False}),
    'addfront2': ('addfront2.y4m', [ZALL], 32, NO_ALARM, MOCK_HAND),
    'addfront2_nohand': ('addfront2_nohand.y4m', [ZALL], 32, NO_ALARM, None, {'ai': False}),
    # بيد: نقل واحد بلا إنذار. بلا يد لا دليل على أنها نفس القطعة؛ المطلوب على الأقل ألا تصبح سرقتين (مكان الوضع ليس سرقة)
    'moveclutter2': ('moveclutter2.y4m', [ZALL], 36, lambda ev: NO_ALARM(ev) and len([1 for _, k, s in ev if k == 'moved' or s == 'moved']) == 1, MOCK_HAND),
    'moveclutter2_nohand': ('moveclutter2_nohand.y4m', [ZALL], 36, lambda ev: len([1 for _, k, s in ev if k == 'removal' and s in ('pending', 'incident')]) <= 1, None, {'ai': False}),
    'turn': ('turn.y4m', [GUM, MOUSE], 28, lambda ev: any(k == 'tamper' for _, k, _ in ev) and not [1 for _, k, _ in ev if k == 'removal'], None),
}


async def run_one(p, name):
    vid, zones, secs, check, mock, *rest = SCENARIOS[name]; cfg = rest[0] if rest else {}
    args = ['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--use-file-for-fake-video-capture=' + os.path.join(OUT, vid)]
    b = await p.chromium.launch(executable_path=CHROME, args=args) if CHROME else await p.chromium.launch(args=args)
    pg = await (await b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)).new_page()
    errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    await pg.goto(HTML); await pg.wait_for_timeout(600)
    import json
    await pg.evaluate("([z, c]) => { S.zones = z; S.cfg.test = true; S.cfg.testSec = 10; Object.assign(S.cfg, c); saveZones(); saveCfg(); }", [zones, cfg])
    if mock:  # الكاشف الوهمي بدل MediaPipe: نمنع تحميل النماذج الحقيقية حتى لا تستبدله لاحقاً، ونحقنه قبل تشغيل الكاميرا
        await pg.evaluate("window.loadMP = async () => {}; window.loadPose = async () => {};")
        await pg.evaluate(mock)
    await pg.click('text=تشغيل الكاميرا')
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
