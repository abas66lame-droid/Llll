/* دوال الخادم لنظام متابعة النظافة
   المصادقة: الموظف يدخل برقمه الوظيفي ورمزه السري. الرمز لا يُخزَّن أبداً في مستند يقرؤه المتصفح؛
   يُحفظ مشفّراً (scrypt + ملح) في مجموعة secrets المغلقة بقواعد الأمان، وتتحقق منه هذه الدوال
   ثم تُصدر رمز دخول (custom token) يحمل: sid (معرّف الموظف) و role و admin. */
const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { setGlobalOptions } = require('firebase-functions/v2');
const { defineString } = require('firebase-functions/params');
const { initializeApp } = require('firebase-admin/app');
const { getFirestore } = require('firebase-admin/firestore');
const { getAuth } = require('firebase-admin/auth');
const crypto = require('crypto');

initializeApp();
setGlobalOptions({ region: 'europe-west1', maxInstances: 10 });

// الحكم الذكي لحارس العارضات (Claude عند كل حدث) — منفصل عن دوال النظافة
exports.judgeEvent = require('./judge').judgeEvent;

// مفتاح الإعداد الأول: يُستخدم مرة واحدة لإنشاء أول مدير، ويُضبط من أسرار GitHub عند النشر
const SETUP_KEY = defineString('SETUP_KEY', { default: '' });

const db = getFirestore();
const PIN_RE = /^\d{4,8}$/;
const MAX_FAILS = 5, LOCK_MS = 15 * 60 * 1000;
const ROLES = ['staff', 'sup', 'insp', 'admin'];

const fail = (code, msg) => { throw new HttpsError(code, msg); };
const clean = (s, n = 80) => String(s == null ? '' : s).trim().slice(0, n);
const hashPin = (pin, salt) => crypto.scryptSync(String(pin), salt, 32).toString('hex');
const same = (a, b) => { const x = Buffer.from(a, 'hex'), y = Buffer.from(b, 'hex'); return x.length === y.length && crypto.timingSafeEqual(x, y); };
const newSecret = pin => { const salt = crypto.randomBytes(16).toString('hex'); return { salt, h: hashPin(pin, salt), fails: 0, lockUntil: 0, at: Date.now() }; };
const newId = () => Date.now().toString(36) + crypto.randomBytes(4).toString('hex');

async function staffByNum(num){
  const n = clean(num, 20); if(!n) return null;
  let s = await db.collection('staff').where('num', '==', n).limit(1).get();
  if(s.empty && /^\d+$/.test(n)) s = await db.collection('staff').where('num', '==', Number(n)).limit(1).get();
  return s.empty ? null : { id: s.docs[0].id, ...s.docs[0].data() };
}
async function cfg(){ const d = await db.doc('config/main').get(); return d.exists ? d.data() : {}; }
function tokenFor(st){
  const role = ROLES.includes(st.role) ? st.role : 'staff';
  return getAuth().createCustomToken('s_' + st.id, { sid: st.id, role, admin: role === 'admin' });
}
function needPin(pin){ if(!PIN_RE.test(String(pin || ''))) fail('invalid-argument', 'الرمز يجب أن يكون من 4 إلى 8 أرقام.'); }
function caller(req){ const t = req.auth && req.auth.token; if(!t || !t.sid) fail('unauthenticated', 'سجّل الدخول أولاً.'); return t; }

// ما الخطوة التالية لهذا الرقم؟ (لا يكشف الاسم ولا أي بيانات)
exports.who = onCall(async req => {
  const st = await staffByNum(req.data && req.data.num);
  if(!st){ const c = await cfg(); return { state: c.selfReg === false ? 'none' : 'reg', setup: !c.setupDone }; }
  if(st.active === false) return { state: 'off' };
  const sec = await db.doc('secrets/' + st.id).get();
  return { state: sec.exists && sec.data().h ? 'pin' : 'newpin' };
});

exports.login = onCall(async req => {
  const { num, pin } = req.data || {};
  needPin(pin);
  const st = await staffByNum(num);
  if(!st || st.active === false) fail('not-found', 'الرقم غير مسجّل أو موقوف.');
  const ref = db.doc('secrets/' + st.id);
  const ok = await db.runTransaction(async tx => {
    const d = await tx.get(ref); const s = d.exists ? d.data() : null;
    if(!s || !s.h) fail('failed-precondition', 'لم يُعيَّن رمز لهذا الحساب بعد.');
    if((s.lockUntil || 0) > Date.now()) fail('resource-exhausted', 'محاولات كثيرة. أعد المحاولة بعد ' + Math.ceil((s.lockUntil - Date.now()) / 60000) + ' دقيقة.');
    if(same(hashPin(pin, s.salt), s.h)){ if(s.fails) tx.update(ref, { fails: 0 }); return true; }
    const f = (s.fails || 0) + 1;
    tx.update(ref, f >= MAX_FAILS ? { fails: 0, lockUntil: Date.now() + LOCK_MS } : { fails: f });
    return false;
  });
  if(!ok) fail('permission-denied', 'الرمز غير صحيح.');
  return { token: await tokenFor(st) };
});

// أول دخول: تعيين الرمز لحساب لم يُفعَّل بعد
exports.setPin = onCall(async req => {
  const { num, pin } = req.data || {};
  needPin(pin);
  const st = await staffByNum(num);
  if(!st || st.active === false) fail('not-found', 'الرقم غير مسجّل أو موقوف.');
  const ref = db.doc('secrets/' + st.id);
  await db.runTransaction(async tx => {
    const d = await tx.get(ref);
    if(d.exists && d.data().h) fail('already-exists', 'الحساب مفعّل مسبقاً. استخدم رمزك.');
    tx.set(ref, newSecret(pin));
    tx.update(db.doc('staff/' + st.id), { activated: true });
  });
  return { token: await tokenFor(st) };
});

exports.changePin = onCall(async req => {
  const t = caller(req), { oldPin, pin } = req.data || {};
  needPin(pin);
  const ref = db.doc('secrets/' + t.sid), d = await ref.get(), s = d.exists ? d.data() : null;
  if(!s || !same(hashPin(String(oldPin || ''), s.salt), s.h)) fail('permission-denied', 'الرمز الحالي غير صحيح.');
  await ref.set(newSecret(pin));
  return { ok: true };
});

// إعادة تعيين رمز موظف: المدير، أو المشرف لموظفي أقسامه
exports.resetPin = onCall(async req => {
  const t = caller(req), id = clean(req.data && req.data.staffId, 64);
  if(!t.admin && t.role !== 'sup') fail('permission-denied', 'لا تملك هذه الصلاحية.');
  const st = await db.doc('staff/' + id).get();
  if(!st.exists) fail('not-found', 'الموظف غير موجود.');
  if(!t.admin){
    const me = (await db.doc('staff/' + t.sid).get()).data() || {};
    const secs = [me.section].concat(me.extra || []).filter(Boolean);
    if(!secs.includes(st.data().section) || st.data().role !== 'staff') fail('permission-denied', 'الموظف خارج أقسامك.');
  }
  await db.doc('secrets/' + id).delete();
  await st.ref.update({ activated: false });
  return { ok: true };
});

// التسجيل الذاتي (إن سمحت به الإدارة)
exports.register = onCall(async req => {
  const d = req.data || {}, num = clean(d.num, 20), name = clean(d.name), section = clean(d.section), branch = clean(d.branch);
  needPin(d.pin);
  if(!/^\d{1,20}$/.test(num) || !name || !section) fail('invalid-argument', 'الرقم والاسم والقسم مطلوبة.');
  if((await cfg()).selfReg === false) fail('permission-denied', 'التسجيل الذاتي غير مسموح.');
  const id = newId(), lock = db.doc('nums/' + num);
  await db.runTransaction(async tx => {
    if((await tx.get(lock)).exists) fail('already-exists', 'الرقم مسجّل مسبقاً.');
    const dup = await tx.get(db.collection('staff').where('num', '==', num).limit(1));
    if(!dup.empty) fail('already-exists', 'الرقم مسجّل مسبقاً.');
    tx.set(lock, { id });
    tx.set(db.doc('staff/' + id), { num, name, section, branch, role: 'staff', active: true, activated: true, self: true, created: Date.now(), st: {} });
    tx.set(db.doc('secrets/' + id), newSecret(d.pin));
  });
  return { token: await tokenFor({ id, role: 'staff' }) };
});

// الإعداد الأول: إنشاء أول مدير. يعمل فقط بمفتاح الإعداد وفقط إذا لم يوجد أي مدير.
exports.bootstrap = onCall(async req => {
  const d = req.data || {}, key = SETUP_KEY.value();
  if(!key || String(d.key || '') !== key) fail('permission-denied', 'مفتاح الإعداد غير صحيح.');
  const num = clean(d.num, 20), name = clean(d.name);
  needPin(d.pin);
  if(!/^\d{1,20}$/.test(num) || !name) fail('invalid-argument', 'الرقم والاسم مطلوبان.');
  const id = newId();
  await db.runTransaction(async tx => {
    const any = await tx.get(db.collection('staff').where('role', '==', 'admin').limit(1));
    if(!any.empty) fail('already-exists', 'تم الإعداد مسبقاً.');
    const c = await tx.get(db.doc('config/main'));
    tx.set(db.doc('staff/' + id), { num, name, section: clean(d.section) || 'الإدارة', branch: clean(d.branch), role: 'admin', active: true, activated: true, created: Date.now(), st: {} });
    tx.set(db.doc('secrets/' + id), newSecret(d.pin));
    tx.set(db.doc('nums/' + num), { id });
    tx.set(db.doc('config/main'), Object.assign({ orgName: clean(d.org) || 'شركة الأماني', requireCode: false, minSec: 30, sens: 1, auditRate: 10, selfReg: false, sound: true, requireLive: true }, c.exists ? c.data() : {}, { setupDone: true }));
  });
  return { token: await tokenFor({ id, role: 'admin' }) };
});
