# اختبار النسخة المبسّطة basit.html بكاميرا وهمية: python3 tests/basit_test.py
import asyncio, os, sys
from playwright.async_api import async_playwright
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'out')
HTML = 'file://' + os.path.abspath(os.path.join(HERE, '..', 'basit.html'))
ZALL = {'x': 0.05, 'y': 0.15, 'w': 0.9, 'h': 0.75}
# (فيديو، المنطقة، الثواني، الحالات المتوقعة، العدد النهائي المتوقع)
CASES = {
    'handtake': ('handtake.y4m', ZALL, 30, ['lack'], 0),       # أُخذ الموبايل: نقص 1←0
    'handmove': ('handmove.y4m', ZALL, 32, ['chg'], 1),        # نُقل: العدد نفسه، تغيّر
    'addfront2': ('addfront2.y4m', ZALL, 30, ['chg'], 4),      # أُضيف موبايل أمام علبة: ليس نقصاً (يلامسها فيُعدّان قطعة واحدة)
    'moveclutter2': ('moveclutter2.y4m', ZALL, 34, ['chg'], 4),# نُقل في عارضة مزدحمة: تغيّر واحد لا نقص
    'nudge2': ('nudge2.y4m', ZALL, 20, None, None),            # ضربة كاميرا بلا شيل: لا «نقص»
}
async def run(p, name):
    vid, z, secs, want, n = CASES[name]
    b = await p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--use-file-for-fake-video-capture=' + os.path.join(OUT, vid)])
    pg = await b.new_page(viewport={'width': 390, 'height': 844}); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    await pg.goto(HTML); await pg.evaluate("z => localStorage.setItem('basit_zone', JSON.stringify(z))", z); await pg.reload()
    await pg.click('button:has-text("تشغيل الكاميرا")'); await pg.wait_for_timeout(secs * 1000)
    got = await pg.evaluate("cases.map(c => c.kind).reverse()"); cnt = await pg.evaluate("lastCount ? lastCount.length : -1"); await b.close()
    ok = (got == want if want is not None else 'lack' not in got) and (n is None or cnt == n) and not errs
    print('PASS' if ok else 'FAIL', name, got, 'count', cnt, errs or ''); return ok
async def main():
    async with async_playwright() as p: r = [await run(p, n) for n in (sys.argv[1:] or CASES)]
    print('%d/%d passed' % (sum(r), len(r))); sys.exit(0 if all(r) else 1)
asyncio.run(main())
