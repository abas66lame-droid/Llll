/* DETECTOR_START */
// ===================== محرك كشف التغيّر (منقول من نسخة بايثون) =====================
const DET = (() => {
  function frameFromCanvas(c){
    const w = c.width, h = c.height, d = c.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, w, h).data, n = w * h;
    const raw = new Float32Array(n), ca = new Float32Array(n), cb = new Float32Array(n);
    for(let i = 0, j = 0; i < n; i++, j += 4){ const R = d[j], G = d[j + 1], B = d[j + 2]; raw[i] = 0.299 * R + 0.587 * G + 0.114 * B; ca[i] = R - G; cb[i] = (R + G) / 2 - B; }
    return build(raw, ca, cb, w, h);
  }
  function build(raw, ca, cb, w, h){
    const g = new Float32Array(w * h);
    for(let y = 0; y < h; y++){ const y0 = y > 0 ? y - 1 : 0, y1 = y < h - 1 ? y + 1 : h - 1;
      for(let x = 0; x < w; x++){ const x0 = x > 0 ? x - 1 : 0, x1 = x < w - 1 ? x + 1 : w - 1;
        g[y * w + x] = (raw[y0 * w + x0] + raw[y0 * w + x] + raw[y0 * w + x1] + raw[y * w + x0] + raw[y * w + x] + raw[y * w + x1] + raw[y1 * w + x0] + raw[y1 * w + x] + raw[y1 * w + x1]) / 9; } }
    const G = grad(g, w, h), W1 = w + 1, I = new Float64Array(W1 * (h + 1));
    for(let y = 0; y < h; y++){ let row = 0; for(let x = 0; x < w; x++){ row += g[y * w + x]; I[(y + 1) * W1 + x + 1] = I[y * W1 + x + 1] + row; } }
    return { w, h, g, ca, cb, G, I };
  }
  function grad(g, w, h){
    const o = new Float32Array(w * h);
    for(let y = 1; y < h - 1; y++) for(let x = 1; x < w - 1; x++){ const i = y * w + x, gx = g[i + 1] - g[i - 1], gy = g[i + w] - g[i - w]; o[i] = Math.sqrt(gx * gx + gy * gy); }
    return o;
  }
  function clone(F){ return { w: F.w, h: F.h, g: F.g.slice(), ca: F.ca.slice(), cb: F.cb.slice(), G: F.G.slice(), I: F.I.slice() }; }
  // اهتزاز الكاميرا: إزاحة صغيرة بدقة ربع الصورة
  function estimateShift(ref, cur){
    const w4 = Math.floor(ref.w / 4), h4 = Math.floor(ref.h / 4), a = new Float32Array(w4 * h4), b = new Float32Array(w4 * h4);
    for(let y = 0; y < h4; y++) for(let x = 0; x < w4; x++){ a[y * w4 + x] = ref.g[y * 4 * ref.w + x * 4]; b[y * w4 + x] = cur.g[y * 4 * cur.w + x * 4]; }
    const ga = grad(a, w4, h4), gb = grad(b, w4, h4), m = 5;
    let best = -2, bd = [0, 0];
    for(let dy = -4; dy <= 4; dy++) for(let dx = -4; dx <= 4; dx++){
      let n = 0, sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0;
      for(let y = m; y < h4 - m; y++) for(let x = m; x < w4 - m; x++){ const A = ga[y * w4 + x], B = gb[(y + dy) * w4 + x + dx]; n++; sa += A; sb += B; saa += A * A; sbb += B * B; sab += A * B; }
      const va = saa - sa * sa / n, vb = sbb - sb * sb / n, c = va > 0 && vb > 0 ? (sab - sa * sb / n) / Math.sqrt(va * vb) : 0;
      if(c > best){ best = c; bd = [dx * 4, dy * 4]; }
    }
    return bd;
  }
  // محاذاة خاصة بكل منطقة: تغيير التركيز في كاميرا الموبايل يقرّب الصورة قليلاً فتنزاح أجزاؤها بمقادير مختلفة
  function zoneShift(ref, cur, z, base){
    const W = ref.w, H = ref.h, x0 = Math.max(14, Math.floor(z.x * W)), y0 = Math.max(14, Math.floor(z.y * H)), x1 = Math.min(W - 14, Math.ceil((z.x + z.w) * W)), y1 = Math.min(H - 14, Math.ceil((z.y + z.h) * H));
    const score = (dx, dy) => { let n = 0, sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0;
      for(let y = y0; y < y1; y += 2){ const yy = y + dy; if(yy < 0 || yy >= H) continue; for(let x = x0; x < x1; x += 2){ const xx = x + dx; if(xx < 0 || xx >= W) continue;
        const A = ref.G[y * W + x], B = cur.G[yy * W + xx]; n++; sa += A; sb += B; saa += A * A; sbb += B * B; sab += A * B; } }
      const va = saa - sa * sa / n, vb = sbb - sb * sb / n; return n > 50 && va > 0 && vb > 0 ? (sab - sa * sb / n) / Math.sqrt(va * vb) : -1; };
    let best = score(base[0], base[1]), bd = base.slice();
    for(let dy = -12; dy <= 12; dy += 3) for(let dx = -12; dx <= 12; dx += 3){ const s = score(dx, dy); if(s > best + 1e-6){ best = s; bd = [dx, dy]; } }
    const c = bd.slice(); for(let dy = -2; dy <= 2; dy++) for(let dx = -2; dx <= 2; dx++){ if(!dx && !dy) continue; const s = score(c[0] + dx, c[1] + dy); if(s > best + 1e-6){ best = s; bd = [c[0] + dx, c[1] + dy]; } }
    return bd;
  }
  // حركة الكاميرا الكاملة (إزاحة + دوران + تقريب): نقيس إزاحة 48 رقعة موزعة على الصورة (من الخشن للدقيق حتى لا تخدعنا
  // الأنماط المتكررة مثل أزرار الكيبورد) ثم نطابقها بتحويل أفيني بطريقة RANSAC (تستبعد الرقع الشاذة مثل مكان قطعة مشالة).
  // يرجع {a,b,c,d,e,f}: u = a·x + c·y + e ، v = b·x + d·y + f (بالبكسل، من المرجع إلى الحالي)، أو null إذا تعذّر القياس بثقة
  function estimateAffine(ref, cur, base){
    const W = ref.w, H = ref.h, w4 = Math.floor(W / 4), h4 = Math.floor(H / 4);
    const down = F => { const o = new Float32Array(w4 * h4);
      for(let y = 0; y < h4; y++) for(let x = 0; x < w4; x++){ let t = 0; for(let yy = 0; yy < 4; yy++){ const r = (y * 4 + yy) * W + x * 4; t += F.g[r] + F.g[r + 1] + F.g[r + 2] + F.g[r + 3]; } o[y * w4 + x] = t / 16; }
      return grad(o, w4, h4); };
    const A4 = down(ref), B4 = down(cur);
    const ncc = (A, B, w, h, x0, y0, x1, y1, dx, dy, st) => { let n = 0, sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0;
      for(let y = y0; y < y1; y += st){ const yy = y + dy; if(yy < 1 || yy >= h - 1) continue; for(let x = x0; x < x1; x += st){ const xx = x + dx; if(xx < 1 || xx >= w - 1) continue;
        const a = A[y * w + x], b = B[yy * w + xx]; n++; sa += a; sb += b; saa += a * a; sbb += b * b; sab += a * b; } }
      const va = saa - sa * sa / n, vb = sbb - sb * sb / n; return n > 40 && va > n * 2 && vb > 0 ? (sab - sa * sb / n) / Math.sqrt(va * vb) : -1; };
    const NX = 8, NY = 6, pts = [], b4 = [Math.round(base[0] / 4), Math.round(base[1] / 4)];
    for(let j = 0; j < NY; j++) for(let i = 0; i < NX; i++){
      const x0 = Math.round(i * w4 / NX), x1 = Math.round((i + 1) * w4 / NX), y0 = Math.round(j * h4 / NY), y1 = Math.round((j + 1) * h4 / NY);
      let best = -1, bd = b4;
      for(let dy = -8; dy <= 8; dy++) for(let dx = -8; dx <= 8; dx++){ const s = ncc(A4, B4, w4, h4, x0, y0, x1, y1, b4[0] + dx, b4[1] + dy, 1); if(s > best){ best = s; bd = [b4[0] + dx, b4[1] + dy]; } }
      if(best < 0.5) continue;
      const X0 = x0 * 4, X1 = x1 * 4, Y0 = y0 * 4, Y1 = y1 * 4; let fb = -1, fd = [bd[0] * 4, bd[1] * 4];
      for(let dy = -4; dy <= 4; dy++) for(let dx = -4; dx <= 4; dx++){ const s = ncc(ref.G, cur.G, W, H, X0, Y0, X1, Y1, bd[0] * 4 + dx, bd[1] * 4 + dy, 2); if(s > fb){ fb = s; fd = [bd[0] * 4 + dx, bd[1] * 4 + dy]; } }
      if(fb > 0.5) pts.push({ x: (X0 + X1) / 2, y: (Y0 + Y1) / 2, u: (X0 + X1) / 2 + fd[0], v: (Y0 + Y1) / 2 + fd[1] });
    }
    const fit = P => { // مربعات صغرى للتحويل الأفيني (حول المتوسط)
      const n = P.length, mx = P.reduce((s, p) => s + p.x, 0) / n, my = P.reduce((s, p) => s + p.y, 0) / n, mu = P.reduce((s, p) => s + p.u, 0) / n, mv = P.reduce((s, p) => s + p.v, 0) / n;
      let xx = 0, xy = 0, yy = 0, xu = 0, yu = 0, xv = 0, yv = 0;
      for(const p of P){ const x = p.x - mx, y = p.y - my, u = p.u - mu, v = p.v - mv; xx += x * x; xy += x * y; yy += y * y; xu += x * u; yu += y * u; xv += x * v; yv += y * v; }
      const det = xx * yy - xy * xy; if(Math.abs(det) < 1e-6 * (xx * yy + 1)) return null;
      const a = (xu * yy - yu * xy) / det, c = (yu * xx - xu * xy) / det, b = (xv * yy - yv * xy) / det, d = (yv * xx - xv * xy) / det;
      return { a, b, c, d, e: mu - a * mx - c * my, f: mv - b * mx - d * my }; };
    const res = (T, p) => Math.hypot(T.a * p.x + T.c * p.y + T.e - p.u, T.b * p.x + T.d * p.y + T.f - p.v);
    const sane = T => T && [T.a - 1, T.d - 1, T.b, T.c].every(v => Math.abs(v) < 0.12);
    const n = pts.length; if(n < 8) return null;
    let bestIn = null;
    for(let i = 0; i < n; i++) for(let j = i + 1; j < n; j++) for(let k = j + 1; k < n; k++){ // كل الثلاثيات (عددها صغير)
      const T = fit([pts[i], pts[j], pts[k]]); if(!sane(T)) continue;
      const In = pts.filter(p => res(T, p) < 3); if(!bestIn || In.length > bestIn.length) bestIn = In;
    }
    if(!bestIn || bestIn.length < Math.max(8, 0.4 * n)) return null;
    let T = fit(bestIn); if(!sane(T)) return null;
    const In = pts.filter(p => res(T, p) < 3); if(In.length >= bestIn.length){ const T2 = fit(In); if(sane(T2)) T = T2; }
    T.inliers = In.length; T.total = n; return T;
  }
  // صحة الصورة: متوسط السطوع ومتوسط قوة الحواف (الملمس). العدسة المغطاة أو المظلمة = ملمس شبه معدوم
  function health(F){ let s = 0, t = 0, n = 0; for(let i = 0; i < F.g.length; i += 7){ s += F.g[i]; t += F.G[i]; n++; } return { mu: s / n, tex: t / n }; }
  // بصمة القطعة (لا تعتمد على المكان ولا الزاوية): بكسلات A التي تختلف عن B داخل المربع = القطعة نفسها
  // (عند الشيل: A = المرجع، B = الحالي؛ عند الظهور: العكس). البصمة = توزيع الألوان (4×4×4) + متوسط الملمس + المساحة
  function itemSig(A, B, box, shift){
    const W = A.w, H = A.h, sx = (shift && shift[0]) || 0, sy = (shift && shift[1]) || 0; // B عند (x+sx, y+sy)
    const x0 = Math.max(2, Math.floor(box.x * W)), y0 = Math.max(2, Math.floor(box.y * H)), x1 = Math.min(W - 2, Math.ceil((box.x + box.w) * W)), y1 = Math.min(H - 2, Math.ceil((box.y + box.h) * H));
    const h = new Float32Array(64); let n = 0, tex = 0;
    const q = (v, lo, hi) => Math.max(0, Math.min(3, Math.floor((v - lo) / (hi - lo) * 4)));
    for(let y = y0; y < y1; y += 2) for(let x = x0; x < x1; x += 2){
      const i = y * W + x, j = Math.min(H - 1, Math.max(0, y + sy)) * W + Math.min(W - 1, Math.max(0, x + sx));
      const dg = Math.abs(A.g[i] - B.g[j]), dc = Math.abs(A.ca[i] - B.ca[j]) + Math.abs(A.cb[i] - B.cb[j]);
      if(dg < 22 && dc < 24) continue;
      h[q(A.g[i], 0, 256) * 16 + q(A.ca[i], -80, 80) * 4 + q(A.cb[i], -80, 80)]++; tex += A.G[i]; n++;
    }
    if(n) for(let k = 0; k < 64; k++) h[k] /= n;
    return { h: Array.from(h), n, tex: n ? tex / n : 0 };
  }
  // توزيع ألوان «الحلقة» المحيطة بالمربع (السطح حول القطعة) بنفس تكميم البصمة: نعرف به أي جانب (قبل/بعد) هو الخلفية وأيهما القطعة
  function ringHist(F, box){
    const W = F.w, H = F.h, gx = box.w * 0.5, gy = box.h * 0.5, h = new Float32Array(64); let n = 0;
    const x0 = Math.max(2, Math.floor((box.x - gx) * W)), y0 = Math.max(2, Math.floor((box.y - gy) * H)), x1 = Math.min(W - 2, Math.ceil((box.x + box.w + gx) * W)), y1 = Math.min(H - 2, Math.ceil((box.y + box.h + gy) * H));
    const bx0 = box.x * W, by0 = box.y * H, bx1 = (box.x + box.w) * W, by1 = (box.y + box.h) * H, q = (v, lo, hi) => Math.max(0, Math.min(3, Math.floor((v - lo) / (hi - lo) * 4)));
    for(let y = y0; y < y1; y += 2) for(let x = x0; x < x1; x += 2){ if(x >= bx0 && x < bx1 && y >= by0 && y < by1) continue; const i = y * W + x; h[q(F.g[i], 0, 256) * 16 + q(F.ca[i], -80, 80) * 4 + q(F.cb[i], -80, 80)]++; n++; }
    if(n) for(let k = 0; k < 64; k++) h[k] /= n;
    return { h: Array.from(h), n };
  }
  // تشابه توزيعين (باتاشاريا) بلا شروط المساحة
  function histSim(a, b){ if(!a || !b || !a.n || !b.n) return 0; let bc = 0; for(let k = 0; k < 64; k++) bc += Math.sqrt(a.h[k] * b.h[k]); return bc; }
  // تشابه بصمتين (0..1): معامل باتاشاريا للألوان، بشرط تقارب المساحة والملمس
  function sigSim(a, b){
    if(!a || !b || a.n < 30 || b.n < 30) return 0;
    // الملمس يُقاس عند بكسلات القطعة وحوافها، والحواف تتغيّر مع السطح الذي تحتها (خشب، قماش)، فالشرط متسامح
    const ar = a.n / b.n, tr = (a.tex + 1) / (b.tex + 1);
    if(ar < 0.4 || ar > 2.5 || tr < 0.4 || tr > 2.5) return 0;
    let bc = 0; for(let k = 0; k < 64; k++) bc += Math.sqrt(a.h[k] * b.h[k]); return bc;
  }
  // «تراجع الصف» لرفوف البضاعة المتكررة (شيبس، شوكولا، علب): القطع متطابقة خلف بعضها، فأخذ القطعة الأمامية لا يُحدث
  // «فراغاً» بل يُرجع واجهة الصف للخلف، فتظهر القطعة التالية أعلى قليلاً في الكاميرا المائلة من الأعلى.
  // نقيس الإزاحة الرأسية لكل كتلة صغيرة: مجموعة كتل ارتفعت معاً = «التقاط» (pick)، ونزلت معاً = «تعبئة» (restock).
  // الإضاءة والضجيج لا يُزيحان شيئاً، والأنماط المتكررة لا تخدعنا لأننا نشترط أن تكون المطابقة المُزاحة أفضل بوضوح من مكانها.
  function recess(ref, cur, z, shift){
    shift = zoneShift(ref, cur, z, shift);
    const W = ref.w, H = ref.h, bs = Math.max(12, Math.min(28, Math.round(z.w * W / 26))), M = 40 + Math.max(Math.abs(shift[0]), Math.abs(shift[1])); // نبتعد عن حافة الصورة بمسافة البحث
    const zx0 = Math.max(M, Math.floor(z.x * W)), zy0 = Math.max(M, Math.floor(z.y * H)), zx1 = Math.min(W - M, Math.ceil((z.x + z.w) * W)), zy1 = Math.min(H - M, Math.ceil((z.y + z.h) * H));
    if(zx1 - zx0 < bs * 2 || zy1 - zy0 < bs * 2) return [];
    const R = Math.max(10, Math.min(36, Math.round(bs * 1.3)));
    const nx = Math.floor((zx1 - zx0) / bs), ny = Math.floor((zy1 - zy0) / bs), dyMap = new Float32Array(nx * ny);
    const ncc = (x0, y0, dx, dy) => { let n = 0, sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0;
      for(let y = y0; y < y0 + bs; y += 2){ const yy = y + dy; if(yy < 1 || yy >= H - 1) return -1; for(let x = x0; x < x0 + bs; x += 2){ const xx = x + dx; if(xx < 1 || xx >= W - 1) return -1;
        const a = ref.G[y * W + x], b = cur.G[yy * W + xx]; n++; sa += a; sb += b; saa += a * a; sbb += b * b; sab += a * b; } }
      const va = saa - sa * sa / n, vb = sbb - sb * sb / n; return va > n * 20 && vb > n * 4 ? (sab - sa * sb / n) / Math.sqrt(va * vb) : -1; };
    for(let j = 0; j < ny; j++) for(let i = 0; i < nx; i++){
      const x0 = zx0 + i * bs, y0 = zy0 + j * bs;
      let s0 = -1; for(const dx of [-2, 0, 2]) for(let dy = -2; dy <= 2; dy++){ const v = ncc(x0, y0, shift[0] + dx, shift[1] + dy); if(v > s0) s0 = v; }
      if(s0 > 0.85) continue; // الكتلة في مكانها: لا شيء تغيّر
      let best = -1, bd = 0;
      for(let dy = -R; dy <= R; dy += 2){ if(Math.abs(dy) < 5) continue; for(const dx of [-2, 0, 2]){ const v = ncc(x0, y0, shift[0] + dx, shift[1] + dy); if(v > best){ best = v; bd = dy; } } }
      for(const dy of [bd - 1, bd + 1]) for(const dx of [-2, 0, 2]){ const v = ncc(x0, y0, shift[0] + dx, shift[1] + dy); if(v > best){ best = v; bd = dy; } }
      if(best > 0.7 && best - s0 > 0.15) dyMap[j * nx + i] = bd;
    }
    // تجميع الكتل المتجاورة بنفس الاتجاه وإزاحة متقاربة
    const seen = new Uint8Array(nx * ny), out = [];
    for(let k = 0; k < nx * ny; k++){
      if(!dyMap[k] || seen[k]) continue;
      const sg = Math.sign(dyMap[k]), q = [k], g = []; seen[k] = 1;
      while(q.length){ const c = q.pop(); g.push(c); const ci = c % nx, cj = (c / nx) | 0;
        for(const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]){ const ii = ci + di, jj = cj + dj; if(ii < 0 || jj < 0 || ii >= nx || jj >= ny) continue; const n2 = jj * nx + ii;
          if(!seen[n2] && dyMap[n2] && Math.sign(dyMap[n2]) === sg && Math.abs(dyMap[n2] - dyMap[c]) <= 6){ seen[n2] = 1; q.push(n2); } } }
      if(g.length < 4) continue;
      let i0 = 1e9, j0 = 1e9, i1 = -1, j1 = -1, sdy = 0; for(const c of g){ const ci = c % nx, cj = (c / nx) | 0; i0 = Math.min(i0, ci); i1 = Math.max(i1, ci); j0 = Math.min(j0, cj); j1 = Math.max(j1, cj); sdy += dyMap[c]; }
      out.push({ type: sg < 0 ? 'pick' : 'restock', cells: g.length, dy: Math.round(sdy / g.length), x: (zx0 + i0 * bs) / W, y: (zy0 + j0 * bs) / H, w: (i1 - i0 + 1) * bs / W, h: (j1 - j0 + 1) * bs / H });
    }
    return out;
  }
  function zoneBox(F, z, fine){
    const W = F.w, H = F.h;
    let x0 = Math.round(z.x * W), y0 = Math.round(z.y * H);
    const zw = Math.max(8, Math.round((z.x + z.w) * W) - x0), zh = Math.max(8, Math.round((z.y + z.h) * H) - y0);
    const cs = fine ? Math.max(6, Math.min(30, Math.round(zw / 32))) : Math.max(10, Math.min(40, Math.round(zw / 20)));
    let nx = Math.max(1, Math.floor(zw / cs)), ny = Math.max(1, Math.floor(zh / cs));
    if(x0 + nx * cs > W) x0 = Math.max(0, W - nx * cs);
    if(y0 + ny * cs > H) y0 = Math.max(0, H - ny * cs);
    nx = Math.min(nx, Math.floor((W - x0) / cs)); ny = Math.min(ny, Math.floor((H - y0) / cs));
    return { x0, y0, cs, nx, ny };
  }
  function compareZone(ref, cur, z, shift, opt){
    const fine = !!(opt && opt.fine);
    shift = zoneShift(ref, cur, z, shift);
    const W = ref.w, H = ref.h, { x0, y0, cs, nx, ny } = zoneBox(ref, z, fine), C = nx * ny, N = cs * cs;
    if(nx < 1 || ny < 1) return { st: [], regions: [], changed: 0, nx: 0, ny: 0 };
    const rm = new Float32Array(C), tr = new Float32Array(C), ra = new Float32Array(C), rb = new Float32Array(C), rsg = new Float64Array(C), rsgg = new Float64Array(C), rsG = new Float64Array(C), rsGG = new Float64Array(C);
    for(let j = 0; j < ny; j++) for(let i = 0; i < nx; i++){
      const k = j * nx + i; let sg = 0, sgg = 0, sG = 0, sGG = 0, sa = 0, sb = 0;
      for(let yy = 0; yy < cs; yy++){ const row = (y0 + j * cs + yy) * W + x0 + i * cs; for(let xx = 0; xx < cs; xx++){ const p = row + xx, a = ref.g[p], A = ref.G[p]; sg += a; sgg += a * a; sG += A; sGG += A * A; sa += ref.ca[p]; sb += ref.cb[p]; } }
      rsg[k] = sg; rsgg[k] = sgg; rsG[k] = sG; rsGG[k] = sGG; rm[k] = sg / N; tr[k] = sG / N; ra[k] = sa / N; rb[k] = sb / N;
    }
    const best = new Float32Array(C).fill(-2), tmin = new Float32Array(C).fill(1e9), tmax = new Float32Array(C), tb = new Float32Array(C), cmb = new Float32Array(C), cab = new Float32Array(C), cbb2 = new Float32Array(C);
    const step = Math.max(1, Math.floor(cs / 6)); let any = false;
    const ncc = (sa, saa, sb, sbb, sab) => { const va = saa - sa * sa / N, vb = sbb - sb * sb / N, den = Math.sqrt(Math.max(0, va) * Math.max(0, vb));
      if(va < 1e-3 && vb < 1e-3) return 1; return den > 1e-3 ? (sab - sa * sb / N) / den : 0; };
    for(const dy of [-step, 0, step]) for(const dx of [-step, 0, step]){
      const ox = dx + shift[0], oy = dy + shift[1];
      if(x0 + ox < 0 || y0 + oy < 0 || x0 + nx * cs + ox > W || y0 + ny * cs + oy > H) continue;
      any = true; const off = oy * W + ox;
      for(let j = 0; j < ny; j++) for(let i = 0; i < nx; i++){
        const k = j * nx + i; let sb = 0, sbb = 0, sab = 0, SB = 0, SBB = 0, SAB = 0, ca = 0, cbb = 0;
        for(let yy = 0; yy < cs; yy++){ const row = (y0 + j * cs + yy) * W + x0 + i * cs;
          for(let xx = 0; xx < cs; xx++){ const p = row + xx, q = p + off, a = ref.g[p], b = cur.g[q], A = ref.G[p], B = cur.G[q];
            sb += b; sbb += b * b; sab += a * b; SB += B; SBB += B * B; SAB += A * B; ca += cur.ca[q]; cbb += cur.cb[q]; } }
        const sim = 0.45 * ncc(rsg[k], rsgg[k], sb, sbb, sab) + 0.55 * ncc(rsG[k], rsGG[k], SB, SBB, SAB), t = SB / N;
        if(sim > best[k]){ tb[k] = t; best[k] = sim; cmb[k] = sb / N; cab[k] = ca / N; cbb2[k] = cbb / N; }
        if(t < tmin[k]) tmin[k] = t; if(t > tmax[k]) tmax[k] = t;
      }
    }
    if(!any) return { st: new Array(C).fill('same'), regions: [], changed: 0, nx, ny };
    // تعويض تغيّر التعريض التلقائي وتوازن الأبيض في كاميرات الموبايل: نقارن بعد إزالة التغيّر العام في المنطقة
    const med = arr => { const a = Array.from(arr).sort((p, q) => p - q); return a.length ? a[a.length >> 1] : 0; };
    // نقدّر التغيّر العام من الخلايا التي لم تتغيّر بنيتها فقط (تشابه عالٍ)، حتى لا يؤثر الشيل نفسه على التقدير
    const ratios = [], da = [], db = []; for(let k = 0; k < C; k++) if(best[k] >= 0.6){ if(rm[k] > 12) ratios.push(cmb[k] / rm[k]); da.push(cab[k] - ra[k]); db.push(cbb2[k] - rb[k]); }
    const gain = ratios.length >= 4 ? med(ratios) : 1, dA = da.length >= 4 ? med(da) : 0, dB = db.length >= 4 ? med(db) : 0;
    const md = new Float32Array(C), cd = new Float32Array(C);
    for(let k = 0; k < C; k++){ md[k] = Math.abs(cmb[k] - gain * rm[k]); cd[k] = Math.hypot(cab[k] - ra[k] - dA, cbb2[k] - rb[k] - dB); }
    const st = new Array(C).fill('same'), strong = new Array(C).fill(false);
    for(let k = 0; k < C; k++){
      const s = best[k], R = tr[k], tc = tb[k], lo = Math.max(R, tc) < (fine ? 3 : 4);
      // الوضع الدقيق (قطع صغيرة): خلايا أصغر وشروط أخف، مع بقاء شرط انخفاض التشابه
      const rem = fine ? (s < 0.5 && tmax[k] < 0.7 * R && R - tmax[k] > 3 && !lo) || (s < 0.4 && cd[k] > 15 && tmax[k] <= R && !lo)
                       : s < 0.5 && tmax[k] < 0.55 * R && tmax[k] < 6 && R - tmax[k] > 5 && !lo;
      const add = !rem && (fine ? (s < 0.5 && R < 0.7 * tmin[k] && tmin[k] - R > 3 && !lo) || (s < 0.4 && cd[k] > 15 && tmin[k] >= R && !lo)
                       : s < 0.5 && R < 0.55 * tmin[k] && R < 6 && tmin[k] - R > 5 && !lo);
      const textured = Math.max(R, tc) > 8, real = Math.abs(R - tc) / Math.max(1, Math.max(R, tc)) > 0.3 || cd[k] > 12 || md[k] > 20;
      const chg = (!lo && !rem && !add && ((s < 0.3 && textured && real) || cd[k] > 24 || md[k] > 35)) || (lo && (md[k] > 20 || cd[k] > 15));
      st[k] = rem ? 'rem' : add ? 'add' : chg ? 'chg' : 'same';
      strong[k] = (rem && tmax[k] < 0.38 * R) || (add && R < 0.38 * tmin[k]);
    }
    // دمج المناطق المتقاربة من نفس النوع (قطعة واحدة قد تنقسم إلى جزأين)
    const gs = group(st, strong, nx, ny, fine);
    const gap = fine ? 2 : 1;
    for(let changed = true; changed;){ changed = false;
      for(let a = 0; a < gs.length && !changed; a++) for(let b = a + 1; b < gs.length && !changed; b++){
        const A = gs[a], B = gs[b];
        if(A.type === B.type && A.i0 <= B.i1 + gap && B.i0 <= A.i1 + gap && A.j0 <= B.j1 + gap && B.j0 <= A.j1 + gap){
          gs[a] = { type: A.type, cells: A.cells + B.cells, i0: Math.min(A.i0, B.i0), j0: Math.min(A.j0, B.j0), i1: Math.max(A.i1, B.i1), j1: Math.max(A.j1, B.j1) }; gs.splice(b, 1); changed = true; } } }
    // منطقة «تغيّر» عامة: نحدد اتجاهها من مجموع التفاصيل قبل وبعد (جسم داكن على سطح داكن مثلاً)
    for(const g of gs){ if(g.type !== 'chg') continue; let a = 0, b = 0, dm = 0, n = 0;
      for(let j = g.j0; j <= g.j1; j++) for(let i = g.i0; i <= g.i1; i++){ const k = j * nx + i; a += tr[k]; b += tb[k]; dm += md[k]; n++; }
      if(a > 1.3 * b && a - b > 1.5 * n) g.type = 'rem'; else if(b > 1.3 * a && b - a > 1.5 * n) g.type = 'add'; }
    const regions = gs.map(r => ({ type: r.type, cells: r.cells,
      x: (x0 + r.i0 * cs) / W, y: (y0 + r.j0 * cs) / H, w: (r.i1 - r.i0 + 1) * cs / W, h: (r.j1 - r.j0 + 1) * cs / H }))
      .map(r => Object.assign(r, { coarse: coarseSim(ref, cur, r, shift) })).filter(r => r.coarse < (opt && opt.keepAll ? 9 : 0.85));
    return { st, regions, changed: st.filter(s => s !== 'same').length / C, nx, ny, x0, y0, cs, W, H, shift };
  }
  function group(st, strong, nx, ny, fine){
    const lab = new Int32Array(nx * ny).fill(-1), comps = [];
    const nb = k => { const i = k % nx, j = (k / nx) | 0, o = []; if(i < nx - 1) o.push(k + 1); if(i > 0) o.push(k - 1); if(j < ny - 1) o.push(k + nx); if(j > 0) o.push(k - nx); return o; };
    const grow = (k, type, ok) => { const id = comps.length, q = [k], mem = []; lab[k] = id; while(q.length){ const c = q.pop(); mem.push(c); for(const n of nb(c)) if(lab[n] < 0 && ok(n)){ lab[n] = id; q.push(n); } } comps.push({ type, mem }); };
    for(let k = 0; k < st.length; k++) if(lab[k] < 0 && strong[k]){ const t = st[k]; grow(k, t, n => strong[n] && st[n] === t); }
    for(let k = 0; k < st.length; k++) if(lab[k] < 0 && (st[k] === 'rem' || st[k] === 'add') && !nb(k).some(n => lab[n] >= 0)){ const t = st[k]; grow(k, t, n => st[n] === t); }
    for(let p = 0; p < 2; p++) for(let k = 0; k < st.length; k++) if(lab[k] < 0 && st[k] !== 'same'){ const n = nb(k).find(n => lab[n] >= 0); if(n !== undefined){ lab[k] = lab[n]; comps[lab[n]].mem.push(k); } }
    for(let k = 0; k < st.length; k++) if(lab[k] < 0 && st[k] === 'chg') grow(k, 'chg', n => st[n] === 'chg' && lab[n] < 0);
    const out = [];
    for(const c of comps){
      if(c.mem.length < (c.type === 'chg' ? (fine ? 3 : 4) : 2)) continue;
      let i0 = 1e9, i1 = -1, j0 = 1e9, j1 = -1;
      for(const m of c.mem){ const i = m % nx, j = (m / nx) | 0; i0 = Math.min(i0, i); i1 = Math.max(i1, i); j0 = Math.min(j0, j); j1 = Math.max(j1, j); }
      if(!fine && (i1 === i0 || j1 === j0) && c.mem.length < 6) continue;   // شريط رفيع بعرض خلية واحدة: غالباً حافة انزاحت قليلاً
      out.push({ type: c.type, cells: c.mem.length, i0, j0, i1, j1 });
    }
    return out;
  }
  // فحص سريع للحركة بين لقطتين (مربعات 16×16، مع تسامح ±2 بكسل وتجاهل تغيّر الإضاءة العام)
  function motion(prev, cur, z, block = 16, thr = 14){
    const W = prev.w, H = prev.h, W1 = W + 1;
    let x0 = Math.max(2, Math.floor(z.x * W)), y0 = Math.max(2, Math.floor(z.y * H));
    let nx = Math.floor(Math.min(W - 2 - x0, Math.floor(z.w * W)) / block), ny = Math.floor(Math.min(H - 2 - y0, Math.floor(z.h * H)) / block);
    if(nx < 1 || ny < 1) return [0, 0];
    const bm = (I, x, y) => (I[(y + block) * W1 + x + block] - I[y * W1 + x + block] - I[(y + block) * W1 + x] + I[y * W1 + x]) / (block * block);
    const n = nx * ny, a = new Float32Array(n), bestd = new Float32Array(n).fill(1e9), diff = new Float32Array(n);
    for(let j = 0; j < ny; j++) for(let i = 0; i < nx; i++) a[j * nx + i] = bm(prev.I, x0 + i * block, y0 + j * block);
    const b = new Float32Array(n), rat = [];
    for(const dy of [-2, 0, 2]) for(const dx of [-2, 0, 2]){
      rat.length = 0;
      for(let j = 0; j < ny; j++) for(let i = 0; i < nx; i++){ const k = j * nx + i; b[k] = bm(cur.I, x0 + i * block + dx, y0 + j * block + dy); if(a[k] > 12) rat.push(b[k] / a[k]); }
      rat.sort((p, q) => p - q); const gain = rat.length ? rat[rat.length >> 1] : 1;   // تغيّر التعريض العام
      for(let k = 0; k < n; k++) diff[k] = b[k] - gain * a[k];
      const med = Array.from(diff).sort((p, q) => p - q)[n >> 1];
      for(let k = 0; k < n; k++) bestd[k] = Math.min(bestd[k], Math.abs(diff[k] - med) / Math.max(1, Math.max(thr, 0.1 * a[k]) / thr));
    }
    let c = 0; for(let k = 0; k < n; k++) if(bestd[k] > thr) c++;
    return [c / n, c];
  }
  function rebase(base, F, z){
    const W = F.w, H = F.h, x0 = Math.max(0, Math.floor(z.x * W)), y0 = Math.max(0, Math.floor(z.y * H));
    const x1 = Math.min(W, Math.round((z.x + z.w) * W) + 1), y1 = Math.min(H, Math.round((z.y + z.h) * H) + 1);
    for(let y = y0; y < y1; y++){ const a = y * W + x0, b = y * W + x1; for(const k of ['g', 'ca', 'cb', 'G']) base[k].set(F[k].subarray(a, b), a); }
    return [x0, y0, x1 - x0, y1 - y0];
  }
  // تحقق بنيوي خشن: نقارن متوسطات مربعات كبيرة داخل المنطقة. تغيّر التركيز (ضبابية) أو تقريب العدسة البسيط لا يغيّر البنية الخشنة،
  // أما شيل قطعة فيغيّرها. يرجع قيمة بين -1 و 1 (كلما ارتفعت كان التغيّر شكلياً لا حقيقياً)
  function coarseSim(ref, cur, reg, shift){
    const W = ref.w, H = ref.h, mx = reg.w * 0.12, my = reg.h * 0.12;
    const x0 = Math.max(0, Math.floor((reg.x - mx) * W)), y0 = Math.max(0, Math.floor((reg.y - my) * H)), x1 = Math.min(W, Math.ceil((reg.x + reg.w + mx) * W)), y1 = Math.min(H, Math.ceil((reg.y + reg.h + my) * H));
    const bw = Math.max(3, Math.round(Math.min(x1 - x0, y1 - y0) / 7)), nx = Math.floor((x1 - x0) / bw), ny = Math.floor((y1 - y0) / bw);
    if(nx < 2 || ny < 2) return 0;
    const means = (F, ox, oy) => { const out = new Float32Array(nx * ny);
      for(let j = 0; j < ny; j++) for(let i = 0; i < nx; i++){ let s = 0, c = 0;
        for(let y = y0 + j * bw + oy; y < y0 + (j + 1) * bw + oy; y++){ if(y < 0 || y >= H) continue; const row = y * W;
          for(let x = x0 + i * bw + ox; x < x0 + (i + 1) * bw + ox; x++){ if(x < 0 || x >= W) continue; s += F.g[row + x]; c++; } }
        out[j * nx + i] = c ? s / c : 0; } return out; };
    const a = means(ref, 0, 0), n = a.length; let ma = 0; for(const v of a) ma += v; ma /= n;
    let va = 0; for(const v of a) va += (v - ma) * (v - ma); va /= n;
    let best = -1; const st = Math.max(1, Math.round(bw / 2));
    for(const dy of [-st, 0, st]) for(const dx of [-st, 0, st]){
      const b = means(cur, dx + shift[0], dy + shift[1]); let mb = 0; for(const v of b) mb += v; mb /= n;
      let vb = 0, cv = 0; for(let k = 0; k < n; k++){ vb += (b[k] - mb) * (b[k] - mb); cv += (a[k] - ma) * (b[k] - mb); } vb /= n; cv /= n;
      let s;
      if(va < 4 && vb < 4) s = 1;                 // الاثنان شبه متجانسين: لا تغيّر بنيوي
      else if(va < 4 || vb < 4) s = 0;            // أحدهما متجانس والآخر فيه تفاصيل: تغيّر حقيقي
      else s = cv / Math.sqrt(va * vb);
      if(s > best) best = s;
    }
    return best;
  }
  const overlap = (a, b) => { const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)), iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)); return ix * iy / Math.max(1e-9, Math.min(a.w * a.h, b.w * b.h)); };
  // صورة مصغّرة رمادية (عرض ثابت) لمطابقة العارضة المحفوظة مع اللقطة الحالية
  function resize(A, w, h, nw, nh){
    const o = new Float32Array(nw * nh), sx = w / nw, sy = h / nh;
    for(let j = 0; j < nh; j++){ const y0 = Math.floor(j * sy), y1 = Math.max(y0 + 1, Math.floor((j + 1) * sy));
      for(let i = 0; i < nw; i++){ const x0 = Math.floor(i * sx), x1 = Math.max(x0 + 1, Math.floor((i + 1) * sx)); let s = 0, c = 0;
        for(let y = y0; y < y1 && y < h; y++) for(let x = x0; x < x1 && x < w; x++){ s += A[y * w + x]; c++; }
        o[j * nw + i] = c ? s / c : 0; } }
    return o;
  }
  function ncc(R, rw, rh, C, cw, ch, tx, ty){
    const x0 = Math.max(0, tx), x1 = Math.min(cw, tx + rw), y0 = Math.max(0, ty), y1 = Math.min(ch, ty + rh);
    const n = (x1 - x0) * (y1 - y0); if(x1 <= x0 || y1 <= y0 || n < 0.5 * rw * rh) return -1;
    let sr = 0, sc = 0, srr = 0, scc = 0, src = 0;
    for(let y = y0; y < y1; y++){ const rr = (y - ty) * rw - tx, cr = y * cw;
      for(let x = x0; x < x1; x++){ const a = R[rr + x], b = C[cr + x]; sr += a; sc += b; srr += a * a; scc += b * b; src += a * b; } }
    const vr = srr - sr * sr / n, vc = scc - sc * sc / n; return vr > 1e-6 && vc > 1e-6 ? (src - sr * sc / n) / Math.sqrt(vr * vc) : -1;
  }
  // أين صارت العارضة المحفوظة في اللقطة الحالية: تكبير s وإزاحة (tx,ty) بنقاط الصورة المصغّرة الحالية (الموبايل قد يكون أقرب/أبعد/مزاحاً)
  function alignThumb(R, rw, rh, C, cw, ch){
    const k = 24 / cw, CW = 24, CH = Math.max(1, Math.round(ch * k)), Cc = resize(C, cw, ch, CW, CH);
    let best = { score: -1 };
    for(let s = 0.6; s <= 1.6001; s += 0.04){
      const w = Math.max(4, Math.round(rw * s * k)), h = Math.max(4, Math.round(rh * s * k)), Rs = resize(R, rw, rh, w, h);
      for(let ty = -Math.round(h / 2); ty <= CH - Math.round(h / 2); ty++) for(let tx = -Math.round(w / 2); tx <= CW - Math.round(w / 2); tx++){
        const v = ncc(Rs, w, h, Cc, CW, CH, tx, ty); if(v > best.score) best = { score: v, s, tx: tx / k, ty: ty / k }; } }
    if(best.score < 0) return null;
    const b0 = best;
    for(let s = b0.s - 0.04; s <= b0.s + 0.0401; s += 0.01){
      const w = Math.round(rw * s), h = Math.round(rh * s), Rs = resize(R, rw, rh, w, h);
      for(let ty = Math.round(b0.ty) - 4; ty <= Math.round(b0.ty) + 4; ty++) for(let tx = Math.round(b0.tx) - 4; tx <= Math.round(b0.tx) + 4; tx++){
        const v = ncc(Rs, w, h, C, cw, ch, tx, ty); if(v > best.score || best === b0) best = { score: v, s: w / rw, sy: h / rh, tx, ty }; } }
    return best;
  }
  // نقل منطقة (نسبية في المرجع) إلى مكانها في اللقطة الحالية
  const mapZone = (z, T, rw, rh, cw, ch) => ({ ...z, x: (T.s * z.x * rw + T.tx) / cw, y: ((T.sy || T.s) * z.y * rh + T.ty) / ch, w: T.s * z.w * rw / cw, h: (T.sy || T.s) * z.h * rh / ch });
  // ميزات منطقة تغيّر (تدريب على RetailAction: كاميرات سقف حقيقية). A = قبل، B = بعد، C = الصورة التالية لـ B (للثبات)، r = المنطقة
  function regionFeats(A, B, C, r){
    const W = A.w, x0 = Math.max(0, Math.floor(r.x * W)), y0 = Math.max(0, Math.floor(r.y * A.h)), x1 = Math.min(W, Math.ceil((r.x + r.w) * W)), y1 = Math.min(A.h, Math.ceil((r.y + r.h) * A.h));
    let n = 0, sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0, Ga = 0, Gb = 0, dC = 0, dg = 0, big = 0, st = 0;
    for(let y = y0; y < y1; y++) for(let x = x0; x < x1; x++){ const p = y * W + x, a = A.g[p], b = B.g[p]; n++; sa += a; sb += b; saa += a * a; sbb += b * b; sab += a * b; Ga += A.G[p]; Gb += B.G[p];
      const dc = Math.hypot(A.ca[p] - B.ca[p], A.cb[p] - B.cb[p]); dC += dc; const d = Math.abs(a - b); dg += d; if(d > 25 || dc > 30) big++; if(C) st += Math.abs(b - C.g[p]); }
    if(!n) return null; const ma = sa / n, mb = sb / n, va = saa / n - ma * ma, vb = sbb / n - mb * mb, cov = sab / n - ma * mb, ncc = va > 1 && vb > 1 ? cov / Math.sqrt(va * vb) : 1, ta = Ga / n, tb = Gb / n;
    return [r.type === 'rem' ? 1 : 0, r.type === 'add' ? 1 : 0, r.type === 'chg' ? 1 : 0, Math.log(r.w * r.h + 1e-6), r.w / Math.max(1e-6, r.h), r.cells || 0,
      ncc, (mb - ma) / 50, Math.sqrt(Math.max(0, va)) / 50, Math.sqrt(Math.max(0, vb)) / 50, (tb - ta) / Math.max(1, ta + tb), ta / 20, tb / 20, dC / n / 30, dg / n / 30, big / n, C ? st / n / 30 : 0];
  }
  // نموذج حركة الإخفاء (مدرَّب على MNNIT Shoplifting 2022، CC BY 4.0): ميزات نافذة من 6 قراءات وضعية (COCO-17: x, y بالبكسل، ثقة)
  // نسخة حرفية من feats.py (norm_frame + window_feats) — تُختبر مطابقتها في tests/unit_detector.js
  const PK = { LSH: 5, RSH: 6, LEL: 7, REL: 8, LWR: 9, RWR: 10, LHIP: 11, RHIP: 12 };
  function poseNorm(k){ // k: 51 رقماً
    const c = i => k[i * 3 + 2], X = i => k[i * 3], Y = i => k[i * 3 + 1];
    if(Math.min(c(PK.LSH), c(PK.RSH), c(PK.LHIP), c(PK.RHIP)) < 0.2) return null;
    const sx = (X(PK.LSH) + X(PK.RSH)) / 2, sy = (Y(PK.LSH) + Y(PK.RSH)) / 2, hx = (X(PK.LHIP) + X(PK.RHIP)) / 2, hy = (Y(PK.LHIP) + Y(PK.RHIP)) / 2, t = Math.hypot(sx - hx, sy - hy);
    if(t < 5) return null;
    const rel = [], conf = []; for(let i = 0; i < 17; i++){ rel.push([(X(i) - hx) / t, (Y(i) - hy) / t]); conf.push(c(i)); } return { rel, conf };
  }
  function poseWindowFeats(seq){ // seq: نتائج poseNorm (بلا null)
    const n = seq.length, d = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]), mean = a => a.reduce((s, v) => s + v, 0) / a.length, std = a => { const m = mean(a); return Math.sqrt(mean(a.map(v => (v - m) * (v - m)))); };
    const side = (w, el, sh, hp) => {
      let p = seq.map(s => s.rel[w]), ok = seq.map(s => s.conf[w] > 0.2);
      if(ok.filter(Boolean).length < 2){ p = p.map(() => [0, 0]); ok = ok.map(() => true); }
      const dh = p.map((q, i) => d(q, seq[i].rel[hp])), dc = p.map(q => Math.hypot(q[0], q[1])), ds = p.map((q, i) => d(q, seq[i].rel[sh]));
      const v = n > 1 ? p.slice(1).map((q, i) => d(q, p[i])) : [0];
      const ea = p.map((q, i) => d(seq[i].rel[el], seq[i].rel[sh]) + d(q, seq[i].rel[el]) - d(q, seq[i].rel[sh]));
      const xs = p.map(q => q[0]), ys = p.map(q => q[1]), inb = mean(p.map(q => (Math.abs(q[0]) < 0.6 && q[1] > -0.9 && q[1] < 0.45) ? 1 : 0));
      return [mean(xs), mean(ys), std(xs), std(ys), Math.min(...ys), Math.max(...ys), Math.min(...dh), mean(dh), Math.min(...dc), mean(dc), Math.max(...ds), Math.max(...v), mean(v), v.reduce((s, x) => s + x, 0),
        p[n - 1][1] - p[0][1], Math.abs(p[n - 1][0] - p[0][0]) + Math.abs(p[n - 1][1] - p[0][1]), Math.min(...ea), mean(ea), inb, mean(ok.map(o => o ? 1 : 0))];
    };
    const a = side(PK.LWR, PK.LEL, PK.LSH, PK.LHIP), b = side(PK.RWR, PK.REL, PK.RSH, PK.RHIP);
    return [...a.map((x, i) => Math.max(x, b[i])), ...a.map((x, i) => Math.min(x, b[i])), mean(seq.map(s => d(s.rel[PK.LWR], s.rel[PK.RWR])))];
  }
  // أشجار HistGradientBoosting مصدَّرة: [feature, threshold, left, right, isLeaf, value, missingLeft]
  // فلتر السقف بالرؤية: ميزات المنطقة + تشابه بصمتي MobileNet (قبل/بعد) + إسقاط PCA لبصمة «بعد» ولفرق البصمتين — نسخة حرفية من emb_train2.py
  function pcaProj(P, v){ const o = []; for(const row of P.comp){ let s = 0; for(let i = 0; i < row.length; i++) s += (v[i] - P.mean[i]) * row[i]; o.push(s); } return o; }
  function visFeats(M, f, eb, ea){ let d = 0; for(let i = 0; i < ea.length; i++) d += eb[i] * ea[i]; const df = ea.map((v, i) => v - eb[i]);
    return [...M.cols.map(i => f[i]), d, ...pcaProj(M.pcaA, ea), ...pcaProj(M.pcaB, df)]; }
  function visProb(M, f, eb, ea){ return treeProb(M, visFeats(M, f, eb, ea)); }
  function treeProb(M, x){ let s = M.base; for(const t of M.trees){ let i = 0; while(!t[i][4]){ const v = x[t[i][0]]; i = (v !== v ? t[i][6] : v <= t[i][1]) ? t[i][2] : t[i][3]; } s += t[i][5]; } return 1 / (1 + Math.exp(-s)); }
  return { poseNorm, poseWindowFeats, treeProb, visFeats, visProb, regionFeats, frameFromCanvas, build, clone, estimateShift, estimateAffine, health, itemSig, sigSim, ringHist, histSim, recess, compareZone, motion, rebase, overlap, coarseSim, resize, alignThumb, mapZone };
})();
/* DETECTOR_END */
if(typeof module !== 'undefined') module.exports = DET;
