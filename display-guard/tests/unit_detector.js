// اختبارات وحدة سريعة لمحرك الكشف بدون متصفح: node tests/unit_detector.js
const D = require('../src/detector.js');
let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
const W = 960, H = 540, zone = { x: 300 / W, y: 180 / H, w: 320 / W, h: 180 / H };
function scene(fn, noise, bright){ const N = W * H, raw = new Float32Array(N), ca = new Float32Array(N), cb = new Float32Array(N);
  for(let y = 0; y < H; y++) for(let x = 0; x < W; x++){ let [R, G, B] = fn(x, y); const n = (rnd() - .5) * 2 * noise; R = R * bright + n; G = G * bright + n; B = B * bright + n;
    const i = y * W + x; raw[i] = .299 * R + .587 * G + .114 * B; ca[i] = R - G; cb[i] = (R + G) / 2 - B; }
  return D.build(raw, ca, cb, W, H); }
const wood = gum => (x, y) => { let R = 150 + 18 * Math.sin(x / 9 + Math.sin(y / 40) * 2) + 8 * Math.sin(y / 3.1);
  if(gum && x >= 430 && x < 476 && y >= 260 && y < 278){ const e = x - 430 < 2 || 476 - x <= 2 || y - 260 < 2 || 278 - y <= 2; return e ? [60, 60, 60] : [225, 230, 235]; } return [R, R * .72, R * .5]; };
const light = gum => (x, y) => (gum && x >= 440 && x < 470 && y >= 270 && y < 282) ? ((x < 442 || x > 467 || y < 272 || y > 279) ? [170, 168, 160] : [238, 236, 230]) : [205, 200, 192];
let fails = 0; const t = (name, cond) => { console.log((cond ? 'PASS ' : 'FAIL ') + name); if(!cond) fails++; };
for(const fine of [false, true]) for(const [nm, f, nz] of [['wood', wood, 5], ['white-on-light', light, 7]]){
  const a = scene(f(true), nz, 1); let fp = 0;
  for(let k = 0; k < 8; k++){ const b = scene(f(true), nz, .96 + .08 * rnd()); fp += D.compareZone(a, b, zone, [0, 0], { fine }).regions.length; }
  const r = D.compareZone(a, scene(f(false), nz, 1), zone, [0, 0], { fine });
  t(`${nm} ${fine ? 'fine' : 'normal'}: no false regions under noise/exposure`, fp === 0);
  t(`${nm} ${fine ? 'fine' : 'normal'}: small item removal detected`, r.regions.some(g => g.type === 'rem'));
}
// حركة الكاميرا: تقدير التحويل الأفيني (إزاحة + دوران + تقريب) على مشهد بنمط متكرر (مثل الكيبورد) وقطعة مشالة
{
  const tex = (x, y) => { const k = (Math.floor(x / 14) + Math.floor(y / 14)) % 2 ? 40 : 0; const v = 120 + 50 * Math.sin(x / 23 + Math.sin(y / 37) * 3) + 30 * Math.sin(y / 17 - x / 51) + (y > 380 ? k : 0); return [v, v * .9, v * .8]; };
  const th = 1.5 * Math.PI / 180, sc = 1.01, A = { a: sc * Math.cos(th), b: sc * Math.sin(th), c: -sc * Math.sin(th), d: sc * Math.cos(th) }; A.e = 14 - (A.a - 1) * 480 - A.c * 270; A.f = 9 - A.b * 480 - (A.d - 1) * 270;
  const det = A.a * A.d - A.b * A.c, inv = (u, v) => { u -= A.e; v -= A.f; return [(A.d * u - A.c * v) / det, (-A.b * u + A.a * v) / det]; };
  const ref = scene(tex, 4, 1), cur = scene((u, v) => { const [x, y] = inv(u, v); return (x >= 430 && x < 520 && y >= 250 && y < 300) ? [200, 60, 60] : tex(x, y); }, 4, 1);
  const t0 = Date.now(), T = D.estimateAffine(ref, cur, D.estimateShift(ref, cur)), ms = Date.now() - t0;
  const err = T ? Math.max(...[[100, 100], [860, 100], [100, 440], [860, 440], [480, 270]].map(([x, y]) => Math.hypot(T.a * x + T.c * y + T.e - (A.a * x + A.c * y + A.e), T.b * x + T.d * y + T.f - (A.b * x + A.d * y + A.f)))) : 1e9;
  t(`camera affine: recovered within 1.5px (max err ${err.toFixed(2)}px, ${ms}ms)`, err < 1.5);
}
// العارضة المحفوظة في لقطة جديدة (الموبايل أبعد ومزاح): المناطق تُنقل لمكانها الجديد
{
  const RW = 96, RH = 170, pat = (x, y) => 120 + 60 * Math.sin(x / 5) * Math.cos(y / 7) + (y > 40 && y < 60 ? 50 : 0) + (x > 20 && x < 35 ? -40 : 0);
  const R = new Float32Array(RW * RH); for(let y = 0; y < RH; y++) for(let x = 0; x < RW; x++) R[y * RW + x] = pat(x, y);
  const s = 0.85, tx = 9, ty = 14, C = new Float32Array(RW * RH);
  for(let y = 0; y < RH; y++) for(let x = 0; x < RW; x++) C[y * RW + x] = pat((x - tx) / s, (y - ty) / s);
  const T = D.alignThumb(R, RW, RH, C, RW, RH), z = D.mapZone({ x: 0.2, y: 0.3, w: 0.5, h: 0.1 }, T, RW, RH, RW, RH);
  const want = { x: (0.2 * RW * s + tx) / RW, y: (0.3 * RH * s + ty) / RH };
  t(`stand re-located after phone moved (scale ${T.s.toFixed(2)}, score ${T.score.toFixed(2)})`, Math.abs(z.x - want.x) < 0.02 && Math.abs(z.y - want.y) < 0.02 && Math.abs(T.s - s) < 0.04);
}
process.exit(fails ? 1 : 0);
