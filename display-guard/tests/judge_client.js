// اختبار الحكم الذكي في صفحة الحارس بخادم وهمي (بلا تكلفة): node tests/judge_client.js
// يتحقق أن الحكم الواثق يصحّح قرار المحرك في الاتجاهين، وأن الحكم الضعيف أو الخطأ لا يغيّر شيئاً.
const { chromium } = require('playwright'), path = require('path');
const HTML = 'file://' + path.resolve(__dirname, '..', 'haris.html');
const V = { 'نقل': ['moved', 0.9], 'أخذ متخفٍّ': ['taken', 0.92], 'سرقة': ['taken', 0.95], 'غير واثق': ['moved', 0.5], 'إخفاء كاذب': ['no_change', 0.85] };
let fails = 0; const t = (name, cond) => { console.log((cond ? 'PASS ' : 'FAIL ') + name); if(!cond) fails++; };
(async () => {
  const b = await chromium.launch(), p = await b.newPage(), errs = [], reqs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.route('https://judge.test/api/judge', async route => {
    const r = route.request(), body = JSON.parse(r.postData()); reqs.push({ key: r.headers()['x-guard-key'], body });
    if(body.ctx.zone === 'مرفوض') return route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ error: 'رمز الربط غير صحيح' }) });
    const [verdict, confidence] = V[body.ctx.zone] || ['unclear', 0];
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ verdict, confidence, item: 'هاتف', summary: 'حكم تجريبي: ' + verdict, risk: 'low', model: 'claude-opus-5-5' }) });
  });
  await p.goto(HTML); await p.waitForTimeout(500);
  await p.evaluate(() => {
    Object.assign(S.cfg, { judge: true, judgeUrl: 'https://judge.test/api/judge', judgeKey: 'k-123' });
    S.zones = ['نقل', 'أخذ متخفٍّ', 'سرقة', 'غير واثق', 'إخفاء كاذب', 'مرفوض'].map((n, i) => ({ id: 'z' + i, name: n, section: '', x: .1, y: .1, w: .3, h: .3 }));
    const c = document.createElement('canvas'); c.width = 320; c.height = 240; c.getContext('2d').fillRect(0, 0, 320, 240); ENG.baseCv = c;
    const reg = { x: .15, y: .15, w: .1, h: .1 }, z = S.zones;
    ENG.newRemoval(z[0], reg, c, false);                      // المحرك: شيل — Claude: نُقلت (90%) => يُغلق «نُقل»
    ENG.newInfo(z[1], reg, 'added', c);                       // المحرك: إضافة — Claude: أُخذت (92%) => يصبح شيلاً بمهلة
    ENG.newRemoval(z[2], reg, c, false);                      // المحرك: شيل — Claude: أُخذت => يبقى معلّقاً
    ENG.newRemoval(z[3], reg, c, false);                      // Claude غير واثق (50%) => لا تغيير
    addEvent({ id: 'cc', zone: 'z4', kind: 'conceal', status: 'incident', t_start: now(), box: reg, img_b: c.toDataURL('image/jpeg'), img_a: c.toDataURL('image/jpeg'), note: '' }); // اشتباه إخفاء — Claude: لا تغيير (85%) => يُغلق
    ENG.newRemoval(z[5], reg, c, false);                      // الخادم يرفض => يبقى قرار المحرك
  });
  await p.waitForTimeout(1500);
  const ev = await p.evaluate(() => Object.fromEntries(S.events.map(e => [zoneOf(e.zone).name, [e.kind, e.status, !!e.ai, e.aiErr || '', e.deadline > now()]])));
  t('removal judged "moved" with high confidence -> closed as moved', ev['نقل'][1] === 'moved');
  t('"added" judged "taken" -> becomes a pending removal with a deadline', ev['أخذ متخفٍّ'][0] === 'removal' && ev['أخذ متخفٍّ'][1] === 'pending' && ev['أخذ متخفٍّ'][4]);
  t('removal judged "taken" -> stays pending', ev['سرقة'][1] === 'pending' && ev['سرقة'][2]);
  t('low confidence -> engine decision kept', ev['غير واثق'][1] === 'pending' && ev['غير واثق'][2]);
  t('conceal judged "no change" (85%) -> closed', ev['إخفاء كاذب'][1] === 'resolved');
  t('server error -> engine decision kept + reason shown', ev['مرفوض'][1] === 'pending' && /رمز الربط/.test(ev['مرفوض'][3]));
  t('requests carry the access code and base64 images without the data: prefix', reqs.length === 6 && reqs.every(r => r.key === 'k-123' && r.body.images.length >= 2 && r.body.images.every(i => !i.data.startsWith('data:'))));
  t('default model is Opus 5.5', reqs.every(r => r.body.model === 'claude-opus-5-5'));
  await p.evaluate(() => { S.tab = 'ev'; S.evf = 'all'; render(); });
  t('event cards show the Claude verdict', (await p.locator('.ai').count()) >= 5);
  await p.evaluate(() => { S.tab = 'set'; render(); });
  t('settings show the smart-judge card', await p.locator('text=الحكم الذكي (Claude)').count() > 0);
  t('no page errors', !errs.length); if(errs.length) console.log(errs);
  await b.close(); process.exit(fails ? 1 : 0);
})();
