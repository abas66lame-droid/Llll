// فحص سريع لـ basit.html: الصفحة تعمل، والتعليم يُحفظ، والتصدير/الاستيراد يعيدان نفس الذاكرة: node tests/basit_smoke.js
const { chromium } = require('playwright'), path = require('path');
(async () => { const b = await chromium.launch(), p = await b.newPage(), errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.goto('file://' + path.resolve(__dirname, '..', 'basit.html'));
  const r = await p.evaluate(() => { cases = [{ id: 'x1', t: Date.now(), kind: 'put', v: [1, 2, 3, 4, 5, 6, 7], before: '', after: '' }]; teach('x1', 'take');
    const k = knn([1, 2, 3, 4, 5, 6, 7]); return [mem.length, mem[0].label, k.label]; });
  const [dl] = await Promise.all([p.waitForEvent('download'), p.evaluate(() => exportMem())]); const f = await dl.path();
  await p.evaluate(() => { mem = []; }); await p.setInputFiles('input[type=file]', f); p.on('dialog', d => d.accept());
  await p.waitForTimeout(500); const n = await p.evaluate(() => mem.length);
  const ok = r[0] === 1 && r[1] === 'take' && r[2] === 'take' && n === 1 && !errs.length; console.log(ok ? 'PASS' : 'FAIL', r, 'imported', n, errs); await b.close(); process.exit(ok ? 0 : 1); })();
