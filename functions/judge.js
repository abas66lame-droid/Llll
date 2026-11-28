/* الحكم الذكي لحارس العارضات: عند كل حدث يرسل الجهاز صوراً صغيرة (قبل / لحظة اليد / بعد)، وClaude يحكم ماذا حدث فعلاً.
   المحرك على الجهاز يبقى المنبّه المجاني الذي يعمل 24 ساعة؛ هذه الدالة تُستدعى عند الأحداث فقط (لا لكل إطار).
   الحماية: رمز ربط مشترك (GUARD_KEY) يُدخله المشرف في إعدادات الحارس، وحد يومي للطلبات، وحدود لحجم الصور.
   المفتاح ANTHROPIC_API_KEY يبقى على الخادم ولا يصل إلى أي موبايل. */
const { onRequest } = require('firebase-functions/v2/https');
const { defineString } = require('firebase-functions/params');
const crypto = require('crypto');
const AnthropicSDK = require('@anthropic-ai/sdk');
const Anthropic = AnthropicSDK.default || AnthropicSDK;

const ANTHROPIC_API_KEY = defineString('ANTHROPIC_API_KEY', { default: '' });
const GUARD_KEY = defineString('GUARD_KEY', { default: '' });
const GUARD_DAILY = defineString('GUARD_DAILY', { default: '3000' });

const MODELS = ['claude-opus-5-5', 'claude-haiku-5-5'];
const VERDICTS = ['taken', 'moved', 'returned', 'added', 'rearranged', 'concealed', 'no_change', 'unclear'];
const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['verdict', 'item', 'summary', 'confidence', 'risk'],
  properties: {
    verdict: { type: 'string', enum: VERDICTS },
    item: { type: 'string', description: 'اسم القطعة بالعربي باختصار، أو نص فارغ إذا لم تُعرف' },
    summary: { type: 'string', description: 'جملة عربية واحدة تصف ما حدث للمشرف' },
    confidence: { type: 'number', description: 'من 0 إلى 1' },
    risk: { type: 'string', enum: ['low', 'medium', 'high'] },
  },
};
const SYSTEM = `You review events from a camera that watches product displays and shelves in an electronics and grocery store in Iraq.
A cheap on-device detector noticed a change and sends you small frames. Decide what really happened to the products.
The detector is often wrong about direction: taking an item can reveal another item behind it (looks like "added"),
and putting a plain item on a patterned surface can look like "removed". Judge from what the frames show, not from the detector's guess.

Verdicts:
- taken: an item that was there is gone from the watched area and is not visible anywhere else in the frames.
- moved: the same item is now somewhere else in view, or only its position or angle changed.
- returned: the item is back in its original place; the scene after matches the scene before.
- added: a new item was placed and nothing is missing.
- rearranged: items were tidied or shifted; nothing is missing.
- concealed: a person put an item into a pocket, bag or clothing.
- no_change: no real product change (lighting, reflection, camera shake, a person or arm passing).
- unclear: the frames do not allow a decision (blocked view, blur).

Answer in Arabic for "item" and "summary": short, plain, written for a store supervisor. "confidence" is your probability (0 to 1)
that the verdict is right. "risk" is how likely this is a theft that needs a human to look now.`;

const LABELS = {
  before: 'المشهد قبل التغيّر (المربع الملوّن يحدد المكان)',
  after: 'المشهد بعد التغيّر',
  compare: 'مقارنة مقرّبة للمكان: اليمين قبل، واليسار بعد',
  hand: 'لحظة وجود اليد أو الشخص عند العارضة',
  dest: 'المكان الذي ظهرت فيه القطعة (إن وُجد)',
};

const clean = (s, n = 200) => String(s == null ? '' : s).replace(/[\u0000-\u001f]/g, ' ').trim().slice(0, n);
const sameKey = (a, b) => { const x = Buffer.from(String(a)), y = Buffer.from(String(b)); return x.length === y.length && crypto.timingSafeEqual(x, y); };
let day = '', used = 0;

// يبني الطلب ويستدعي Claude ويرجع الحكم بعد التحقق منه. يُختبر محلياً بعميل وهمي (client).
async function judge(body, client){
  const model = MODELS.includes(body.model) ? body.model : MODELS[0];
  const images = (Array.isArray(body.images) ? body.images : []).slice(0, 4).filter(im => im && LABELS[im.label] && /^[A-Za-z0-9+/=]+$/.test(im.data || '') && im.data.length < 700000);
  if(!images.length) return { status: 400, out: { error: 'لا توجد صور صالحة' } };
  const c = body.ctx || {};
  const ctx = [
    'العارضة: ' + clean(c.zone, 80) + (c.mode === 'stock' ? ' (رف بضاعة متكررة: قطع متطابقة خلف بعضها)' : ' (عارضة أجهزة وقطع منفردة)'),
    'تخمين المحرك على الجهاز: ' + clean(c.guess, 40) + (c.hand ? '، ورُصدت يد عند المكان' : '، ولم تُرصد يد'),
    c.note ? 'ملاحظة المحرك: ' + clean(c.note, 300) : '',
    c.noSales ? 'لا يوجد بيع حالياً في المحل: أي قطعة تُؤخذ ولا ترجع تُعتبر مشكلة.' : '',
    // (تجربة RetailAction: كاميرات سقف حقيقية) هذا التوجيه بجانب السؤال ضاعف الإنذارات الكاذبة المُزالة بلا خسارة سرقات
    'الكاميرا غالباً عالية أو في السقف والقطع صغيرة. رأس شخص أو كتفه أو ملابسه أو حقيبته أو ظله داخل المربع ليس قطعة (no_change). أما إذا كان مكان على الرف فيه منتج في «قبل» وصار فارغاً في «بعد» فهذا أخذ (taken) حتى لو كانت القطعة صغيرة.',
  ].filter(Boolean).join('\n');
  const content = [];
  for(const im of images){ content.push({ type: 'text', text: LABELS[im.label] + ':' }); content.push({ type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data: im.data } }); }
  content.push({ type: 'text', text: ctx + '\n\nماذا حدث للقطع؟' });
  const req = { model, max_tokens: 4000, system: SYSTEM, output_config: { effort: 'medium', format: { type: 'json_schema', schema: SCHEMA } }, messages: [{ role: 'user', content }] };
  // Opus 5.5: عند رفض نادر من مصنّفات الأمان يُعاد الطلب تلقائياً على النموذج البديل الموصى به (Haiku 5.5 لا يدعم ذلك)
  const res = model === 'claude-opus-5-5'
    ? await client.beta.messages.create({ ...req, betas: ['server-side-fallback-2026-07-01'], fallbacks: 'default' })
    : await client.messages.create(req);
  if(res.stop_reason === 'refusal') return { status: 200, out: { verdict: 'unclear', item: '', summary: 'رفض النموذج الحكم على هذه الصور.', confidence: 0, risk: 'medium', model: res.model } };
  if(res.stop_reason === 'max_tokens') return { status: 200, out: { verdict: 'unclear', item: '', summary: 'لم يكتمل الحكم.', confidence: 0, risk: 'medium', model: res.model } };
  const txt = (res.content || []).filter(b => b.type === 'text').map(b => b.text).join('');
  let v; try{ v = JSON.parse(txt); }catch(e){ return { status: 502, out: { error: 'رد غير مفهوم من النموذج' } }; }
  return { status: 200, out: {
    verdict: VERDICTS.includes(v.verdict) ? v.verdict : 'unclear', item: clean(v.item, 60), summary: clean(v.summary, 300),
    confidence: Math.max(0, Math.min(1, Number(v.confidence) || 0)), risk: ['low', 'medium', 'high'].includes(v.risk) ? v.risk : 'medium', model: res.model,
    usage: res.usage ? { in: res.usage.input_tokens, out: res.usage.output_tokens } : undefined } };
}

async function handle(req, res, makeClient){
  if(req.method !== 'POST') return res.status(405).json({ error: 'POST فقط' });
  const key = GUARD_KEY.value(), apiKey = ANTHROPIC_API_KEY.value();
  if(!key || !apiKey) return res.status(503).json({ error: 'الحكم الذكي غير مُعدّ على الخادم (ANTHROPIC_API_KEY و GUARD_KEY)' });
  if(!sameKey(req.get('x-guard-key') || '', key)) return res.status(401).json({ error: 'رمز الربط غير صحيح' });
  const body = req.body || {};
  if(body.ping) return res.json({ ok: true, models: MODELS });
  const d = new Date().toISOString().slice(0, 10); if(d !== day){ day = d; used = 0; }
  if(++used > (parseInt(GUARD_DAILY.value(), 10) || 3000)) return res.status(429).json({ error: 'تجاوز الحد اليومي للطلبات' });
  try{
    const r = await judge(body, makeClient(apiKey));
    res.status(r.status).json(r.out);
  }catch(e){
    // الأخطاء المؤقتة (ازدحام، خادم) يعيد الجهاز المحاولة لاحقاً؛ غيرها لا
    if(e instanceof Anthropic.RateLimitError) return res.status(429).json({ error: 'ازدحام، أعد المحاولة لاحقاً' });
    if(e instanceof Anthropic.AuthenticationError) return res.status(503).json({ error: 'مفتاح Anthropic على الخادم غير صالح' });
    if(e instanceof Anthropic.BadRequestError) return res.status(400).json({ error: 'طلب غير صالح: ' + clean(e.message, 200) });
    if(e instanceof Anthropic.APIError) return res.status(502).json({ error: 'خطأ من خدمة Claude (' + e.status + ')' });
    console.error(e); res.status(500).json({ error: 'خطأ في الخادم' });
  }
}

exports.judge = judge;
exports.handle = handle;
exports.judgeEvent = onRequest({ cors: true, timeoutSeconds: 120, memory: '256MiB' }, (req, res) => handle(req, res, apiKey => new Anthropic({ apiKey, maxRetries: 2 })));
