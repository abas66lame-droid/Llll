# basit.html بكاميرا وهمية: يجب أن تظهر حالة عند الشيل والنقل، ولا شيء بلا تغيير: python3 tests/basit_cam.py
import asyncio, os, sys
from playwright.async_api import async_playwright
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'out'); HTML = 'file://' + os.path.abspath(os.path.join(HERE, '..', 'basit.html'))
Z = {'x': 0.05, 'y': 0.15, 'w': 0.9, 'h': 0.75}
CASES = {'noisy': ('handtake_noisy.y4m', 30, lambda k: len(k) >= 1), 'handtake': ('handtake.y4m', 30, lambda k: len(k) >= 1), 'handmove': ('handmove.y4m', 32, lambda k: len(k) >= 1), 'stockidle': ('stockidle.y4m', 25, lambda k: len(k) == 0)}
async def run(p, name):
    vid, secs, ok = CASES[name]
    b = await p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--use-file-for-fake-video-capture=' + os.path.join(OUT, vid)])
    pg = await b.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    await pg.goto(HTML); await pg.evaluate("z => localStorage.setItem('basit_zone', JSON.stringify(z))", Z); await pg.reload()
    await pg.click('button:has-text("تشغيل الكاميرا")'); await pg.wait_for_timeout(secs * 1000)
    k = await pg.evaluate("cases.map(c => c.kind)"); st = await pg.evaluate("document.querySelector('#st').textContent"); await b.close()
    r = ok(k) and not errs; print('PASS' if r else 'FAIL', name, k, st, errs or ''); return r
async def main():
    async with async_playwright() as p: r = [await run(p, n) for n in (sys.argv[1:] or CASES)]
    print('%d/%d passed' % (sum(r), len(r))); sys.exit(0 if all(r) else 1)
asyncio.run(main())
