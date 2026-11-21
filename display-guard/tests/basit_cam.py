# النسخة المبسّطة basit.html (نفس محرك الحارس): رسم العارضة بالإصبع بلا أسئلة، ثم شيل = حالة نقص تتحول تنبيهاً،
# ويد وهمية (كاشف أيادٍ) تؤجّل الحكم: python3 tests/basit_cam.py
import asyncio, os, sys, re
from playwright.async_api import async_playwright
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'out'); HTML = 'file://' + os.path.abspath(os.path.join(HERE, '..', 'basit.html'))
MOCK_HAND = re.search(r'MOCK_HAND = r"""(.*?)"""', open(os.path.join(HERE, 'run_scenarios.py'), encoding='utf-8').read(), re.S).group(1)
CASES = {'handtake': ('handtake.y4m', 34, lambda ev: ('removal', 'incident') in ev), 'handmove': ('handmove.y4m', 34, lambda ev: not [1 for k, s in ev if k == 'removal' and s in ('pending', 'incident')]),
         'stockidle': ('stockidle.y4m', 25, lambda ev: not ev)}
async def run(p, name):
    vid, secs, ok = CASES[name]
    b = await p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--use-file-for-fake-video-capture=' + os.path.join(OUT, vid)])
    pg = await (await b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)).new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    await pg.goto(HTML); await pg.evaluate("window.loadMP = async () => {}; window.loadPose = async () => {};"); await pg.evaluate(MOCK_HAND)
    await pg.click('button:has-text("تشغيل الكاميرا")'); await pg.wait_for_timeout(1500)
    await pg.click('text=رسم عارضة'); await pg.wait_for_timeout(300)
    box = await pg.locator('#drawCv').bounding_box(); x0, y0 = box['x'] + box['width'] * .06, box['y'] + box['height'] * .16
    await pg.mouse.move(x0, y0); await pg.mouse.down(); await pg.mouse.move(box['x'] + box['width'] * .94, box['y'] + box['height'] * .9, steps=8); await pg.mouse.up()
    await pg.wait_for_timeout(secs * 1000)
    ev = await pg.evaluate("S.events.map(e => [e.kind, e.status])"); nz = await pg.evaluate("S.zones.length"); modal = await pg.evaluate("!!document.querySelector('#modal').innerHTML"); await b.close()
    ev = [tuple(e) for e in ev]; r = ok(ev) and nz == 1 and not modal and not errs
    print('PASS' if r else 'FAIL', name, ev, 'zones', nz, 'modal', modal, errs or ''); return r
async def main():
    async with async_playwright() as p: r = [await run(p, n) for n in (sys.argv[1:] or CASES)]
    print('%d/%d passed' % (sum(r), len(r))); sys.exit(0 if all(r) else 1)
asyncio.run(main())
