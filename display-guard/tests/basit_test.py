# اختبار النسخة المبسّطة basit.html بكاميرا وهمية وClaude وهمي (بلا تكلفة): python3 tests/basit_test.py
# Claude الوهمي يرد بحسب الفيديو (ما يفترض أن يراه)، فالاختبار يتحقق من: متى تُرسل الصور، وكيف يُطبَّق الرد.
import asyncio, os, sys, json
from playwright.async_api import async_playwright
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'out')
HTML = 'file://' + os.path.abspath(os.path.join(HERE, '..', 'basit.html'))
ZALL = {'x': 0.05, 'y': 0.15, 'w': 0.9, 'h': 0.75}
# (فيديو، ثوانٍ، رد Claude عند المقارنة، الحالات المتوقعة، العدد النهائي)
CASES = {
    'handtake': ('handtake.y4m', 30, {'before': 1, 'after': 0, 'verdict': 'missing', 'summary': 'أُخذ الموبايل.'}, ['lack'], 0),
    'handmove': ('handmove.y4m', 32, {'before': 1, 'after': 1, 'verdict': 'changed', 'summary': 'نُقل الموبايل.'}, ['chg'], 1),
    'stockidle': ('stockidle.y4m', 25, None, [], 1),  # لا تغيّر: لا يُسأل Claude عن مقارنة أصلاً
}
async def run(p, name):
    vid, secs, verdict, want, n = CASES[name]; calls = []
    b = await p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--use-file-for-fake-video-capture=' + os.path.join(OUT, vid)])
    pg = await b.new_page(viewport={'width': 390, 'height': 844}); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
    async def fake(route):
        body = json.loads(route.request.post_data)
        if PROV == 'local': imgs = len(body['messages'][0]['images'])
        else: imgs = sum(1 for c in body['messages'][0]['content'] if c['type'] == 'image')
        calls.append(imgs); out = json.dumps({'count': 1} if imgs == 1 else verdict, ensure_ascii=False)
        if PROV == 'local': resp = {'message': {'role': 'assistant', 'content': out}, 'done': True}
        else: resp = {'id': 'm', 'type': 'message', 'role': 'assistant', 'model': 'claude-opus-5-5', 'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': out}], 'usage': {'input_tokens': 1, 'output_tokens': 1}}
        await route.fulfill(status=200, content_type='application/json', body=json.dumps(resp))
    await pg.route('https://api.anthropic.com/**', fake); await pg.route('http://192.168.1.20:11434/**', fake)
    await pg.goto(HTML); await pg.evaluate("z => { localStorage.setItem('basit_zone', JSON.stringify(z)); localStorage.setItem('basit_key', JSON.stringify('sk-test')); localStorage.setItem('basit_url', JSON.stringify('http://192.168.1.20:11434')); localStorage.setItem('basit_prov', JSON.stringify(z.prov)); }", dict(ZALL, prov=PROV)); await pg.reload()
    await pg.click('button:has-text("تشغيل الكاميرا")'); await pg.wait_for_timeout(secs * 1000)
    st = await pg.evaluate("(() => { const s = state(); return [s.cases.map(c => c.kind).reverse(), s.base ? s.base.n : null]; })()"); await b.close()
    ok = st[0] == want and st[1] == n and not errs and calls[0] == 1 and (not verdict or 2 in calls)
    print('PASS' if ok else 'FAIL', name, st, 'calls', calls, errs or ''); return ok
PROV = os.environ.get('PROV', 'local')  # local = كمبيوتر المحل (Ollama)، claude
async def main():
    async with async_playwright() as p: r = [await run(p, n) for n in (sys.argv[1:] or CASES)]
    print('%d/%d passed' % (sum(r), len(r))); sys.exit(0 if all(r) else 1)
asyncio.run(main())
