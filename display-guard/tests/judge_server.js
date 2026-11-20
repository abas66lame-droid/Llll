// اختبار دالة الحكم الذكي على الخادم بعميل Claude وهمي (بلا اتصال ولا تكلفة): node tests/judge_server.js
process.env.GUARD_KEY = 'test-guard'; process.env.ANTHROPIC_API_KEY = 'test-key'; process.env.GUARD_DAILY = '5';
const J = require('../../functions/judge.js');
let fails = 0; const t = (name, cond) => { console.log((cond ? 'PASS ' : 'FAIL ') + name); if(!cond) fails++; };
const img = Buffer.from('fakejpeg').toString('base64');
const fake = reply => { const calls = []; const mk = kind => ({ create: async r => { calls.push({ kind, r }); return typeof reply === 'function' ? reply(r) : reply; } }); return { calls, messages: mk('std'), beta: { messages: mk('beta') } }; };
const ok = v => ({ stop_reason: 'end_turn', model: 'claude-opus-5-5', content: [{ type: 'text', text: JSON.stringify(v) }], usage: { input_tokens: 1500, output_tokens: 300 } });
const res = () => { const o = { code: 200 }; o.status = c => { o.code = c; return o; }; o.json = b => { o.body = b; return o; }; return o; };
const req = (body, key = 'test-guard', method = 'POST') => ({ method, body, get: h => h === 'x-guard-key' ? key : '' });
(async () => {
  // بناء الطلب
  let c = fake(ok({ verdict: 'moved', item: 'هاتف أسود', summary: 'نُقل الهاتف من الرف العلوي إلى السفلي.', confidence: 0.9, risk: 'low' }));
  let r = await J.judge({ images: [{ label: 'before', data: img }, { label: 'hand', data: img }, { label: 'after', data: img }, { label: 'bogus', data: img }], ctx: { zone: 'عارضة', guess: 'removal', hand: true } }, c);
  const q = c.calls[0];
  t('Opus 5.5 by default via beta with server-side fallbacks', q.kind === 'beta' && q.r.model === 'claude-opus-5-5' && q.r.fallbacks === 'default' && q.r.betas.includes('server-side-fallback-2026-07-01'));
  t('structured output schema + effort', q.r.output_config.format.type === 'json_schema' && q.r.output_config.effort === 'medium');
  t('only labelled images are sent (3 of 4), each preceded by its label', q.r.messages[0].content.filter(b => b.type === 'image').length === 3 && q.r.messages[0].content[0].type === 'text');
  t('verdict parsed and returned', r.status === 200 && r.out.verdict === 'moved' && r.out.confidence === 0.9 && r.out.item === 'هاتف أسود');
  // Haiku: بلا fallbacks
  c = fake(ok({ verdict: 'taken', item: '', summary: 'أُخذت القطعة.', confidence: 0.8, risk: 'high' }));
  r = await J.judge({ model: 'claude-haiku-5-5', images: [{ label: 'compare', data: img }] }, c);
  t('Haiku 5.5 uses the standard endpoint without fallbacks', c.calls[0].kind === 'std' && !('fallbacks' in c.calls[0].r) && r.out.verdict === 'taken');
  // رفض، وقيم غريبة، وصور غير صالحة
  r = await J.judge({ images: [{ label: 'before', data: img }] }, fake({ stop_reason: 'refusal', model: 'x', content: [] }));
  t('refusal -> unclear, not an exception', r.status === 200 && r.out.verdict === 'unclear');
  r = await J.judge({ images: [{ label: 'before', data: img }] }, fake(ok({ verdict: 'hack', item: 'x', summary: 's', confidence: 7, risk: 'boom' })));
  t('unknown values are clamped', r.out.verdict === 'unclear' && r.out.confidence === 1 && r.out.risk === 'medium');
  r = await J.judge({ images: [{ label: 'before', data: 'not base64 !!' }] }, fake(ok({})));
  t('invalid images rejected', r.status === 400);
  // HTTP: المصادقة والحد اليومي والفحص
  let o = res(); await J.handle(req({ ping: true }, 'wrong'), o, () => fake(ok({}))); t('wrong guard key -> 401', o.code === 401);
  o = res(); await J.handle(req({ ping: true }), o, () => fake(ok({}))); t('ping -> ok without calling Claude', o.code === 200 && o.body.ok);
  o = res(); await J.handle(req({}, 'test-guard', 'GET'), o, () => fake(ok({}))); t('GET -> 405', o.code === 405);
  let last; for(let i = 0; i < 6; i++){ last = res(); await J.handle(req({ images: [{ label: 'before', data: img }] }), last, () => fake(ok({ verdict: 'no_change', item: '', summary: 's', confidence: .9, risk: 'low' }))); }
  t('daily limit -> 429', last.code === 429);
  process.exit(fails ? 1 : 0);
})();
