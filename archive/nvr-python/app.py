# -*- coding: utf-8 -*-
"""
حارس العارضات — نظام كشف النقص والاختفاء غير المبرر من العارضات عبر كاميرات المراقبة.

التشغيل:
    python app.py            (التشغيل العادي مع كاميرات هكفيجن حسب config.json)
    python app.py --demo     (وضع تجريبي بكاميرات افتراضية، بدون أي ربط)
ثم افتح المتصفح على: http://localhost:8080
"""
import argparse
import datetime
import io
import json
import mimetypes
import os
import socket
import sqlite3
import sys
import threading
import time
import traceback
import urllib.request
import uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

from PIL import Image, ImageDraw

import detector as D
import demo as DM
from sources import HikvisionClient, HikvisionSource, FolderSource

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, 'static')

DEFAULTS = {
    'site_name': 'الفرع الرئيسي',
    'port': 8080,
    'pin': '',
    'poll_seconds': 20,
    'grace_minutes': 20,
    'cleaning_minutes': 15,
    'sale_window_minutes': 30,
    'late_sale_hours': 24,
    'open_time': '09:00',
    'close_time': '23:00',
    'night_alarm': True,
    'analysis_width': 960,
    'telegram': {'token': '', 'chat_id': ''},
    'nvrs': [],
    'cameras': [],
}

STATUS_AR = {'pending': 'ضمن المهلة', 'returned': 'رجع إلى مكانه', 'sold': 'مُباع', 'incident': 'اختفاء غير مبرر',
             'resolved': 'تمت المعالجة', 'info': 'معلومة'}


def now():
    return time.time()


def rid():
    return uuid.uuid4().hex[:12]


def log(*a):
    print(datetime.datetime.now().strftime('%H:%M:%S'), *a, flush=True)


# ===================== التخزين =====================
class DB:
    def __init__(self, path):
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.c.executescript('''
            create table if not exists zones(id text primary key, camera text, name text, section text, x real, y real, w real, h real, created real);
            create table if not exists events(id text primary key, zone text, camera text, kind text, status text, t_start real, t_end real,
                deadline real, box text, img_b text, img_a text, note text, resolution text, resolved_by text, t_resolved real, sale text);
            create table if not exists sales(id text primary key, zone text, qty integer, remaining integer, t real, ref text, source text);
            create table if not exists cleaning(id text primary key, zone text, t_start real, t_end real, who text);
            create index if not exists ev_status on events(status);
            create index if not exists ev_time on events(t_start);
            create index if not exists ev_zone on events(zone);
            ''')
            try:
                self.c.execute('alter table events add column img_c text')
            except sqlite3.OperationalError:
                pass
            self.c.commit()

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.c.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        with self.lock:
            self.c.execute(sql, args)
            self.c.commit()


# ===================== التنبيهات (تيليجرام) =====================
def telegram_send(token, chat_id, text, photo_path=None):
    if not token or not chat_id:
        return False, 'غير مُعدّ'
    try:
        if photo_path and os.path.exists(photo_path):
            boundary = uuid.uuid4().hex
            parts = []
            for k, v in (('chat_id', str(chat_id)), ('caption', text[:1000])):
                parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (boundary, k, v)).encode('utf-8'))
            with open(photo_path, 'rb') as f:
                img = f.read()
            parts.append(('--%s\r\nContent-Disposition: form-data; name="photo"; filename="e.jpg"\r\nContent-Type: image/jpeg\r\n\r\n' % boundary).encode() + img + b'\r\n')
            parts.append(('--%s--\r\n' % boundary).encode())
            req = urllib.request.Request('https://api.telegram.org/bot%s/sendPhoto' % token, data=b''.join(parts),
                                         headers={'Content-Type': 'multipart/form-data; boundary=%s' % boundary})
        else:
            req = urllib.request.Request('https://api.telegram.org/bot%s/sendMessage' % token,
                                         data=json.dumps({'chat_id': chat_id, 'text': text}).encode('utf-8'),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200, 'تم الإرسال'
    except Exception as e:
        return False, str(e)


# ===================== المحرك =====================
class Engine:
    def __init__(self, cfg_path, demo=False):
        self.cfg_path = cfg_path
        self.demo = demo
        self.data = os.path.join(BASE, 'data_demo' if demo else 'data')
        self.evd = os.path.join(self.data, 'evidence')
        os.makedirs(self.evd, exist_ok=True)
        self.cfg = self.load_cfg()
        self.db = DB(os.path.join(self.data, 'haris.db'))
        self.workers = {}
        self.lock = threading.RLock()
        self.last_alert = 0
        self.alert_seq = 0
        if demo:
            self.setup_demo()

    # ---- الإعدادات ----
    def load_cfg(self):
        cfg = json.loads(json.dumps(DEFAULTS))
        if os.path.exists(self.cfg_path):
            try:
                with open(self.cfg_path, encoding='utf-8') as f:
                    user = json.load(f)
                cfg.update(user)
            except Exception as e:
                log('تعذّرت قراءة الإعدادات:', e)
        if self.demo:
            cfg.update({'site_name': 'تجربة — كاميرات افتراضية', 'poll_seconds': 2, 'grace_minutes': 0.5, 'cleaning_minutes': 1.3,
                        'sale_window_minutes': 2, 'open_time': '00:00', 'close_time': '23:59', 'night_alarm': False,
                        'cameras': [{'id': 'demo1', 'name': 'كاميرا تجريبية 1', 'source': 'demo', 'enabled': True},
                                    {'id': 'demo2', 'name': 'كاميرا تجريبية 2', 'source': 'demo', 'enabled': True}], 'nvrs': []})
        return cfg

    def save_cfg(self, new):
        if self.demo:
            raise RuntimeError('لا تُحفظ الإعدادات في الوضع التجريبي')
        cfg = json.loads(json.dumps(DEFAULTS))
        cfg.update(new)
        tmp = self.cfg_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.cfg_path)
        self.cfg = cfg
        self.restart_workers()

    def setup_demo(self):
        for cam in self.cfg['cameras']:
            if not self.db.q('select id from zones where camera=?', (cam['id'],)):
                for z in DM.DEMO_ZONES:
                    self.db.x('insert into zones values(?,?,?,?,?,?,?,?,?)', (rid(), cam['id'], z['name'], z['section'], z['x'], z['y'], z['w'], z['h'], now()))

    # ---- العمال ----
    def make_source(self, cam):
        src = cam.get('source', 'hikvision')
        if src == 'demo':
            s = DM.DemoSource(seed=hash(cam['id']) % 1000)
            zones = self.zones(cam['id'])
            zid = lambda i: zones[i]['id'] if i < len(zones) else None
            g = self.cfg['grace_minutes'] * 60
            s.director = DM.DemoDirector(s.scene, cam['id'], g,
                                         lambda c, zi, q: zid(zi) and self.add_sale(zid(zi), q, 'محاكاة كاشير', 'demo'),
                                         lambda c, zi: zid(zi) and self.start_cleaning(zid(zi), self.cfg['cleaning_minutes'], 'محاكاة'),
                                         offset=0 if cam['id'] == 'demo1' else 25)
            return s
        if src == 'folder':
            return FolderSource(cam.get('path', ''))
        nvr = next((n for n in self.cfg.get('nvrs', []) if n.get('id') == cam.get('nvr')), None)
        if not nvr:
            raise RuntimeError('الـ NVR المرتبط بالكاميرا غير موجود في الإعدادات')
        cli = HikvisionClient(nvr['host'], nvr.get('port', 80), nvr.get('user', 'admin'), nvr.get('password', ''), nvr.get('https', False))
        return HikvisionSource(cli, cam.get('channel', 1), cam.get('stream', 1))

    def start(self):
        self.restart_workers()
        threading.Thread(target=self.ticker, daemon=True).start()

    def restart_workers(self):
        with self.lock:
            for w in self.workers.values():
                w.stop = True
            self.workers = {}
            for cam in self.cfg.get('cameras', []):
                if cam.get('enabled', True):
                    w = CamWorker(self, cam)
                    self.workers[cam['id']] = w
                    w.start()

    # ---- البيانات ----
    def zones(self, cam=None):
        if cam:
            return self.db.q('select * from zones where camera=? order by created', (cam,))
        return self.db.q('select * from zones order by camera, created')

    def zone(self, zid):
        r = self.db.q('select * from zones where id=?', (zid,))
        return r[0] if r else None

    def cleaning_until(self, zid):
        r = self.db.q('select max(t_end) m from cleaning where zone=?', (zid,))
        return (r[0]['m'] or 0) if r else 0

    def is_night(self, t=None):
        if not self.cfg.get('night_alarm', True):
            return False
        t = datetime.datetime.fromtimestamp(t or now())
        cur = t.hour * 60 + t.minute
        def mins(s):
            h, m = (s or '00:00').split(':')
            return int(h) * 60 + int(m)
        o, c = mins(self.cfg['open_time']), mins(self.cfg['close_time'])
        if o == c:
            return False
        is_open = (o <= cur < c) if o < c else (cur >= o or cur < c)
        return not is_open

    def open_events(self, zid):
        return self.db.q("select * from events where zone=? and status in ('pending','incident') order by t_start", (zid,))

    def save_evidence(self, img, box, color, name):
        im = img.copy().convert('RGB')
        d = ImageDraw.Draw(im)
        W, H = im.size
        x0, y0 = box['x'] * W, box['y'] * H
        x1, y1 = x0 + box['w'] * W, y0 + box['h'] * H
        for k in range(4):
            d.rectangle([x0 - k, y0 - k, x1 + k, y1 + k], outline=color)
        d.rectangle([0, 0, W, 26], fill=(0, 0, 0))
        d.text((8, 7), datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), fill=(255, 255, 255))
        fn = name + '.jpg'
        im.save(os.path.join(self.evd, fn), quality=80)
        return fn

    def save_crop(self, img_b, img_a, box, name):
        """صورة مقرّبة: المكان قبل وبعد جنباً إلى جنب (أوضح على الموبايل وفي تيليجرام)."""
        W, H = img_b.size
        px, py = box['w'] * 0.35, box['h'] * 0.35
        x0 = max(0, int((box['x'] - px) * W)); y0 = max(0, int((box['y'] - py) * H))
        x1 = min(W, int((box['x'] + box['w'] + px) * W)); y1 = min(H, int((box['y'] + box['h'] + py) * H))
        a, b = img_b.crop((x0, y0, x1, y1)), img_a.crop((x0, y0, x1, y1))
        h = 300
        a = a.resize((max(1, int(a.width * h / max(1, a.height))), h)); b = b.resize((max(1, int(b.width * h / max(1, b.height))), h))
        out = Image.new('RGB', (a.width + b.width + 12, h + 30), (255, 255, 255))
        out.paste(b, (0, 30)); out.paste(a, (b.width + 12, 30))
        d = ImageDraw.Draw(out)
        d.text((b.width + 18, 8), 'BEFORE', fill=(30, 30, 30)); d.text((6, 8), 'AFTER', fill=(200, 30, 30))
        fn = name + '_c.jpg'
        out.save(os.path.join(self.evd, fn), quality=82)
        return fn

    # ---- الأحداث ----
    def new_removal(self, cam, zone, reg, img_before, img_after, night):
        eid = rid()
        b = self.save_evidence(img_before, reg, (220, 40, 40), eid + '_b')
        a = self.save_evidence(img_after, reg, (220, 40, 40), eid + '_a')
        cimg = self.save_crop(img_before, img_after, reg, eid)
        t = now()
        kind = 'night' if night else 'removal'
        cu = self.cleaning_until(zone['id'])
        deadline = t + self.cfg['grace_minutes'] * 60
        if cu > t:
            deadline = max(deadline, cu + 60)
        status = 'incident' if night else 'pending'
        self.db.x('insert into events(id,zone,camera,kind,status,t_start,deadline,box,img_b,img_a,img_c,note) values(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (eid, zone['id'], cam['id'], kind, status, t, deadline, json.dumps(reg), b, a, cimg,
                   'رُصد بعد ساعات العمل' if night else ''))
        log('نقص جديد', zone['name'], 'ليلي' if night else '')
        # بيع مسجّل مسبقاً خلال النافذة؟
        if not night:
            self.try_match_sale(eid, zone['id'], t)
        if night:
            self.alert(eid)

    def new_info(self, cam, zone, reg, kind, img_before, img_after):
        eid = rid()
        b = self.save_evidence(img_before, reg, (230, 160, 30), eid + '_b')
        a = self.save_evidence(img_after, reg, (40, 160, 80), eid + '_a')
        self.db.x('insert into events(id,zone,camera,kind,status,t_start,t_end,box,img_b,img_a) values(?,?,?,?,?,?,?,?,?,?)',
                  (eid, zone['id'], cam['id'], kind, 'info', now(), now(), json.dumps(reg), b, a))

    def mark_returned(self, ev, img_after, reg):
        a = self.save_evidence(img_after, json.loads(ev['box']), (40, 160, 80), ev['id'] + '_r')
        if ev['status'] == 'pending':
            self.db.x("update events set status='returned', t_end=?, img_a=? where id=?", (now(), a, ev['id']))
            log('رجع إلى مكانه خلال المهلة')
        else:
            # كان تنبيهاً ثم رجع المنتج: يُغلق تلقائياً مع ملاحظة (يبقى ظاهراً في السجل والتقارير)
            self.db.x("update events set status='resolved', resolution='returned', resolved_by='النظام', t_resolved=?, t_end=?, img_a=?, "
                      "note=trim(coalesce(note,'') || ' عاد المنتج إلى مكانه بعد التنبيه') where id=?", (now(), now(), a, ev['id']))

    def try_match_sale(self, eid, zid, t):
        w = self.cfg['sale_window_minutes'] * 60
        s = self.db.q('select * from sales where zone=? and remaining>0 and t>=? order by t limit 1', (zid, t - w))
        if s:
            s = s[0]
            self.db.x('update sales set remaining=remaining-1 where id=?', (s['id'],))
            self.db.x("update events set status='sold', t_end=?, sale=? where id=?", (now(), s['id'], eid))
            return True
        return False

    def add_sale(self, zid, qty, ref='', source='يدوي'):
        if not self.zone(zid):
            raise RuntimeError('المنطقة غير موجودة')
        qty = max(1, min(100, int(qty or 1)))
        sid = rid()
        self.db.x('insert into sales values(?,?,?,?,?,?,?)', (sid, zid, qty, qty, now(), ref or '', source))
        # البيع يبرّر النواقص المفتوحة (ضمن المهلة أو تنبيهات حديثة)
        late = now() - self.cfg['late_sale_hours'] * 3600
        evs = self.db.q("select * from events where zone=? and kind='removal' and (status='pending' or (status='incident' and t_start>=?)) order by t_start", (zid, late))
        used = 0
        for ev in evs[:qty]:
            note = 'بيع متأخر بعد التنبيه' if ev['status'] == 'incident' else ''
            self.db.x("update events set status='sold', t_end=?, sale=?, note=trim(coalesce(note,'') || ' ' || ?) where id=?", (now(), sid, note, ev['id']))
            used += 1
        if used:
            self.db.x('update sales set remaining=remaining-? where id=?', (used, sid))
        return sid

    def start_cleaning(self, zid, minutes, who=''):
        t = now()
        end = t + float(minutes) * 60
        self.db.x('insert into cleaning values(?,?,?,?,?)', (rid(), zid, t, end, who or ''))
        self.db.x("update events set deadline=max(deadline, ?) where zone=? and status='pending'", (end + 60, zid))

    def resolve(self, eid, resolution, note='', who=''):
        self.db.x("update events set status='resolved', resolution=?, note=trim(coalesce(note,'') || ' ' || ?), resolved_by=?, t_resolved=? where id=?",
                  (resolution, note or '', who or '', now(), eid))

    def ticker(self):
        """فحص المهل المنتهية كل ثانيتين."""
        while True:
            try:
                t = now()
                for ev in self.db.q("select * from events where status='pending' and deadline<=?", (t,)):
                    if self.try_match_sale(ev['id'], ev['zone'], ev['t_start']):
                        continue
                    cu = self.cleaning_until(ev['zone'])
                    if cu > t:
                        self.db.x('update events set deadline=? where id=?', (cu + 60, ev['id']))
                        continue
                    self.db.x("update events set status='incident' where id=?", (ev['id'],))
                    log('تنبيه: اختفاء غير مبرر')
                    self.alert(ev['id'])
            except Exception:
                traceback.print_exc()
            time.sleep(2)

    def alert(self, eid):
        self.alert_seq += 1
        ev = self.db.q('select * from events where id=?', (eid,))
        if not ev:
            return
        ev = ev[0]
        z = self.zone(ev['zone']) or {'name': '؟', 'section': ''}
        cam = next((c for c in self.cfg['cameras'] if c['id'] == ev['camera']), {'name': ev['camera']})
        tg = self.cfg.get('telegram') or {}
        if tg.get('token') and tg.get('chat_id'):
            txt = '⚠️ %s\nالفرع: %s\nالعارضة: %s (%s)\nالكاميرا: %s\nالوقت: %s\nمنتج اختفى ولم يُسجَّل بيعه ولم يرجع خلال المهلة.' % (
                'تنبيه ليلي' if ev['kind'] == 'night' else 'اختفاء غير مبرر', self.cfg['site_name'], z['name'], z.get('section', ''),
                cam.get('name', ''), datetime.datetime.fromtimestamp(ev['t_start']).strftime('%Y-%m-%d %H:%M'))
            threading.Thread(target=telegram_send, args=(tg['token'], tg['chat_id'], txt, os.path.join(self.evd, ev.get('img_c') or ev['img_a'] or '')), daemon=True).start()


class CamWorker(threading.Thread):
    def __init__(self, eng, cam):
        super().__init__(daemon=True)
        self.eng, self.cam = eng, cam
        self.stop = False
        self.base = None
        self.prev = None
        self.jpeg = None
        self.last_ts = 0
        self.error = ''
        self.zstate = {}
        self.src = None

    def run(self):
        while not self.stop:
            t0 = time.time()
            try:
                if self.src is None:
                    self.src = self.eng.make_source(self.cam)
                img = self.src.fetch()
                self.process(img)
                self.error = ''
            except Exception as e:
                self.error = str(e)
                if 'NVR' in self.error or 'غير موجود' in self.error:
                    self.src = None
            time.sleep(max(0.5, self.eng.cfg['poll_seconds'] - (time.time() - t0)))

    def process(self, img):
        e = self.eng
        arr = D.to_arrays(img, width=int(e.cfg.get('analysis_width', 960)))
        buf = io.BytesIO()
        arr['img'].save(buf, 'JPEG', quality=72)
        self.jpeg = buf.getvalue()
        self.last_ts = now()
        if self.base is None or self.base['w'] != arr['w'] or self.base['h'] != arr['h']:
            self.base, self.prev = arr, arr
            return
        sh_base = D.estimate_shift(self.base, arr)
        night = e.is_night()
        for z in e.zones(self.cam['id']):
            zs = self.zstate.setdefault(z['id'], {'big': 0})
            # 1) الاستقرار: لا نحكم على المنطقة إذا كان فيها حركة (زبون/موظف يمر)
            # نوسّع المنطقة قليلاً حتى نلتقط شخصاً واقفاً على حافتها
            ez = {'x': max(0, z['x'] - 0.04), 'y': max(0, z['y'] - 0.04)}
            ez['w'] = min(1 - ez['x'], z['w'] + 0.08); ez['h'] = min(1 - ez['y'], z['h'] + 0.08)
            frac, cnt = D.motion(self.prev, arr, ez)
            if frac > 0.01 or cnt >= 3:
                zs['moving'] = True
                continue
            zs['moving'] = False
            # 2) المقارنة مع آخر حالة معتمدة للعارضة
            r = D.compare_zone(self.base, arr, z, sh_base)
            if r['changed'] > 0.5:
                # تغيّر كبير جداً: حجب أو إعادة ترتيب كاملة؛ ننتظر 3 قراءات مستقرة قبل اعتماده
                zs['big'] += 1
                if zs['big'] < 3:
                    continue
                full = {'x': z['x'], 'y': z['y'], 'w': z['w'], 'h': z['h']}
                if night:
                    e.new_removal(self.cam, z, full, self.base['img'], arr['img'], True)
                else:
                    e.new_info(self.cam, z, full, 'major', self.base['img'], arr['img'])
                zs['big'] = 0
                self.rebase(z, arr)
                continue
            zs['big'] = 0
            opened = e.open_events(z['id'])
            handled = set()
            for reg in r['regions']:
                if reg['type'] == 'rem':
                    if any(D.overlap(reg, json.loads(ev['box'])) > 0.5 for ev in opened):
                        continue
                    e.new_removal(self.cam, z, reg, self.base['img'], arr['img'], night)
                else:
                    match = [ev for ev in opened if D.overlap(reg, json.loads(ev['box'])) > 0.35]
                    if match:
                        for ev in match:
                            if ev['id'] not in handled:
                                handled.add(ev['id'])
                                e.mark_returned(ev, arr['img'], reg)
                    else:
                        e.new_info(self.cam, z, reg, 'added' if reg['type'] == 'add' else 'swap', self.base['img'], arr['img'])
            self.rebase(z, arr)
        self.prev = arr

    def rebase(self, z, arr):
        """تحديث الحالة المعتمدة للمنطقة إلى الصورة الحالية."""
        W, H = arr['w'], arr['h']
        # بدون هامش: حتى لا تُكتب أجزاء من مناطق مجاورة من لقطة مختلفة
        x0 = max(0, int(z['x'] * W)); y0 = max(0, int(z['y'] * H))
        x1 = min(W, int(round((z['x'] + z['w']) * W)) + 1); y1 = min(H, int(round((z['y'] + z['h']) * H)) + 1)
        nb = {k: (self.base[k].copy() if k in ('g', 'ca', 'cb') else self.base[k]) for k in self.base}
        for k in ('g', 'ca', 'cb'):
            nb[k][y0:y1, x0:x1] = arr[k][y0:y1, x0:x1]
        im = self.base['img'].copy()
        im.paste(arr['img'].crop((x0, y0, x1, y1)), (x0, y0))
        nb['img'] = im
        self.base = nb


# ===================== خادم الويب =====================
def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def make_handler(eng):
    class H(BaseHTTPRequestHandler):
        server_version = 'Haris/1.0'

        def log_message(self, *a):
            pass

        def send_json(self, obj, code=200):
            b = json.dumps(obj, ensure_ascii=False, default=str).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def send_bytes(self, b, ct, cache=False):
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Cache-Control', 'max-age=86400' if cache else 'no-store')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def body(self):
            n = int(self.headers.get('Content-Length') or 0)
            if n > 2_000_000:
                raise RuntimeError('الطلب كبير جداً')
            raw = self.rfile.read(n) if n else b''
            return json.loads(raw.decode('utf-8')) if raw else {}

        def pin_ok(self):
            p = str(eng.cfg.get('pin') or '')
            return not p or self.headers.get('X-Pin', '') == p

        def do_GET(self):
            try:
                u = urlparse(self.path)
                p = u.path
                qs = {k: v[0] for k, v in parse_qs(u.query).items()}
                if p == '/' or p == '/index.html':
                    with open(os.path.join(STATIC, 'index.html'), 'rb') as f:
                        return self.send_bytes(f.read(), 'text/html; charset=utf-8')
                if p.startswith('/evidence/'):
                    fn = os.path.basename(unquote(p[len('/evidence/'):]))
                    fp = os.path.join(eng.evd, fn)
                    if not os.path.exists(fp):
                        return self.send_json({'error': 'غير موجود'}, 404)
                    with open(fp, 'rb') as f:
                        return self.send_bytes(f.read(), 'image/jpeg', cache=True)
                if p.startswith('/api/frame/'):
                    w = eng.workers.get(p.split('/')[-1])
                    if not w or not w.jpeg:
                        return self.send_json({'error': 'لا توجد صورة بعد'}, 404)
                    return self.send_bytes(w.jpeg, 'image/jpeg')
                if p == '/api/state':
                    return self.send_json(api_state(eng))
                if p == '/api/events':
                    return self.send_json(api_events(eng, qs))
                if p == '/api/zones':
                    return self.send_json(eng.zones(qs.get('camera')))
                if p == '/api/sales':
                    return self.send_json(eng.db.q('select s.*, z.name zname from sales s left join zones z on z.id=s.zone order by t desc limit 100'))
                if p == '/api/report':
                    return self.send_json(api_report(eng, int(qs.get('days', 14))))
                if p == '/api/config':
                    if not self.pin_ok():
                        return self.send_json({'error': 'رمز الإدارة غير صحيح', 'pin': True}, 403)
                    return self.send_json({'cfg': eng.cfg, 'demo': eng.demo})
                return self.send_json({'error': 'غير موجود'}, 404)
            except BrokenPipeError:
                pass
            except Exception as e:
                traceback.print_exc()
                self.send_json({'error': str(e)}, 500)

        def do_POST(self):
            try:
                p = urlparse(self.path).path
                b = self.body()
                open_actions = ('/api/sale', '/api/cleaning')
                if p not in open_actions and not self.pin_ok():
                    return self.send_json({'error': 'رمز الإدارة غير صحيح', 'pin': True}, 403)
                if p == '/api/sale':
                    return self.send_json({'ok': True, 'id': eng.add_sale(b.get('zone'), b.get('qty', 1), b.get('ref', ''), b.get('source', 'يدوي'))})
                if p == '/api/sales/import':
                    n, bad = 0, []
                    zones = eng.zones()
                    for line in (b.get('text') or '').splitlines():
                        parts = [x.strip() for x in line.replace('،', ',').replace('\t', ',').split(',')]
                        if not parts or not parts[0]:
                            continue
                        z = next((z for z in zones if z['id'] == parts[0] or z['name'] == parts[0]), None)
                        if not z:
                            bad.append(parts[0]); continue
                        eng.add_sale(z['id'], parts[1] if len(parts) > 1 and parts[1].isdigit() else 1, parts[2] if len(parts) > 2 else '', 'استيراد')
                        n += 1
                    return self.send_json({'ok': True, 'n': n, 'bad': bad})
                if p == '/api/cleaning':
                    if not eng.zone(b.get('zone')):
                        return self.send_json({'error': 'المنطقة غير موجودة'}, 400)
                    eng.start_cleaning(b['zone'], float(b.get('minutes') or eng.cfg['cleaning_minutes']), b.get('who', ''))
                    return self.send_json({'ok': True})
                if p.startswith('/api/events/') and p.endswith('/resolve'):
                    eid = p.split('/')[3]
                    eng.resolve(eid, b.get('resolution', ''), b.get('note', ''), b.get('who', ''))
                    return self.send_json({'ok': True})
                if p == '/api/zones':
                    zid = b.get('id') or rid()
                    vals = [float(b.get(k, 0)) for k in ('x', 'y', 'w', 'h')]
                    if vals[2] < 0.02 or vals[3] < 0.02:
                        return self.send_json({'error': 'المنطقة صغيرة جداً'}, 400)
                    if eng.zone(zid):
                        eng.db.x('update zones set name=?, section=?, x=?, y=?, w=?, h=? where id=?', (b.get('name', ''), b.get('section', ''), *vals, zid))
                    else:
                        eng.db.x('insert into zones values(?,?,?,?,?,?,?,?,?)', (zid, b.get('camera'), b.get('name', ''), b.get('section', ''), *vals, now()))
                    return self.send_json({'ok': True, 'id': zid})
                if p.startswith('/api/zones/') and p.endswith('/delete'):
                    eng.db.x('delete from zones where id=?', (p.split('/')[3],))
                    return self.send_json({'ok': True})
                if p == '/api/config':
                    eng.save_cfg(b)
                    return self.send_json({'ok': True})
                if p == '/api/nvr/test':
                    cli = HikvisionClient(b.get('host', ''), b.get('port', 80), b.get('user', 'admin'), b.get('password', ''), bool(b.get('https')))
                    info = cli.device_info()
                    chans = cli.channels()
                    return self.send_json({'ok': True, 'device': info, 'channels': chans})
                if p == '/api/telegram/test':
                    tg = b if b.get('token') else (eng.cfg.get('telegram') or {})
                    ok, msg = telegram_send(tg.get('token'), tg.get('chat_id'), '✅ رسالة اختبار من نظام حارس العارضات — %s' % eng.cfg['site_name'])
                    return self.send_json({'ok': ok, 'msg': msg})
                return self.send_json({'error': 'غير موجود'}, 404)
            except Exception as e:
                self.send_json({'error': str(e)}, 400)
    return H


def ev_public(eng, ev, zmap, cmap):
    z = zmap.get(ev['zone'], {})
    ev = dict(ev)
    ev['zone_name'] = z.get('name', 'منطقة محذوفة')
    ev['section'] = z.get('section', '')
    ev['camera_name'] = cmap.get(ev['camera'], ev['camera'])
    ev['status_ar'] = STATUS_AR.get(ev['status'], ev['status'])
    ev['box'] = json.loads(ev['box']) if ev.get('box') else None
    return ev


def api_events(eng, qs):
    st = qs.get('status', 'open')
    lim = min(500, int(qs.get('limit', 100)))
    where, args = [], []
    if st == 'open':
        where.append("status in ('pending','incident')")
    elif st == 'incident':
        where.append("status='incident'")
    elif st == 'pending':
        where.append("status='pending'")
    elif st == 'removals':
        where.append("kind in ('removal','night')")
    elif st == 'info':
        where.append("status='info'")
    if qs.get('zone'):
        where.append('zone=?'); args.append(qs['zone'])
    sql = 'select * from events' + (' where ' + ' and '.join(where) if where else '') + ' order by t_start desc limit %d' % lim
    zmap = {z['id']: z for z in eng.zones()}
    cmap = {c['id']: c.get('name', c['id']) for c in eng.cfg['cameras']}
    return [ev_public(eng, e, zmap, cmap) for e in eng.db.q(sql, args)]


def api_state(eng):
    t0 = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    cams = []
    for c in eng.cfg['cameras']:
        w = eng.workers.get(c['id'])
        cams.append({'id': c['id'], 'name': c.get('name', c['id']), 'source': c.get('source', 'hikvision'), 'enabled': c.get('enabled', True),
                     'ok': bool(w and w.jpeg and not w.error and now() - w.last_ts < eng.cfg['poll_seconds'] * 3 + 10),
                     'error': w.error if w else '', 'last_ts': w.last_ts if w else 0,
                     'moving': [zid for zid, s in (w.zstate.items() if w else []) if s.get('moving')]})
    zones = eng.zones()
    opn = eng.db.q("select zone, status, count(*) n from events where status in ('pending','incident') group by zone, status")
    for z in zones:
        z['pending'] = sum(o['n'] for o in opn if o['zone'] == z['id'] and o['status'] == 'pending')
        z['incident'] = sum(o['n'] for o in opn if o['zone'] == z['id'] and o['status'] == 'incident')
        z['cleaning_until'] = eng.cleaning_until(z['id'])
    c = lambda sql, a=(): eng.db.q(sql, a)[0]['n']
    counts = {
        'pending': c("select count(*) n from events where status='pending'"),
        'incident': c("select count(*) n from events where status='incident'"),
        'today_removals': c("select count(*) n from events where kind in ('removal','night') and t_start>=?", (t0,)),
        'today_returned': c("select count(*) n from events where status='returned' and t_start>=?", (t0,)),
        'today_sold': c("select count(*) n from events where status='sold' and t_start>=?", (t0,)),
        'today_incidents': c("select count(*) n from events where kind in ('removal','night') and (status='incident' or (status='resolved')) and t_start>=?", (t0,)),
    }
    return {'site': eng.cfg['site_name'], 'demo': eng.demo, 'now': now(), 'night': eng.is_night(), 'cameras': cams, 'zones': zones,
            'counts': counts, 'alert_seq': eng.alert_seq, 'grace_minutes': eng.cfg['grace_minutes'], 'cleaning_minutes': eng.cfg['cleaning_minutes'],
            'pin': bool(eng.cfg.get('pin'))}


def api_report(eng, days):
    out = []
    today = datetime.date.today()
    for i in range(days - 1, -1, -1):
        d = today - datetime.timedelta(days=i)
        a = datetime.datetime.combine(d, datetime.time()).timestamp()
        b = a + 86400
        rows = eng.db.q("select status, resolution, count(*) n from events where kind in ('removal','night') and t_start>=? and t_start<? group by status, resolution", (a, b))
        g = lambda f: sum(r['n'] for r in rows if f(r))
        out.append({'day': d.isoformat(), 'removals': g(lambda r: True), 'returned': g(lambda r: r['status'] == 'returned'),
                    'sold': g(lambda r: r['status'] == 'sold' or r['resolution'] == 'sold'),
                    'incidents': g(lambda r: r['status'] == 'incident' or r['status'] == 'resolved'),
                    'theft': g(lambda r: r['resolution'] == 'theft'), 'false': g(lambda r: r['resolution'] == 'false'),
                    'late_return': g(lambda r: r['resolution'] == 'returned')})
    since = time.time() - days * 86400
    zrows = eng.db.q("""select z.name, z.section, count(*) total,
        sum(case when e.status in ('incident','resolved') then 1 else 0 end) incidents,
        sum(case when e.resolution='theft' then 1 else 0 end) theft
        from events e join zones z on z.id=e.zone where e.kind in ('removal','night') and e.t_start>=? group by e.zone order by incidents desc, total desc limit 30""", (since,))
    return {'days': out, 'zones': zrows}


def main():
    ap = argparse.ArgumentParser(description='حارس العارضات')
    ap.add_argument('--demo', action='store_true', help='وضع تجريبي بكاميرات افتراضية')
    ap.add_argument('--config', default=os.path.join(BASE, 'config.json'))
    ap.add_argument('--port', type=int, default=0)
    ap.add_argument('--grace', type=float, default=0, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.demo and not os.path.exists(args.config):
        with open(args.config, 'w', encoding='utf-8') as f:
            json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
    eng = Engine(args.config, demo=args.demo)
    if args.grace:
        eng.cfg['grace_minutes'] = args.grace
        eng.cfg['cleaning_minutes'] = args.grace * 2.6
    eng.start()
    port = args.port or int(eng.cfg.get('port', 8080))
    try:
        srv = ThreadingHTTPServer(('0.0.0.0', port), make_handler(eng))
    except OSError:
        log('المنفذ %d مستخدم من برنامج آخر. غيّر "port" في config.json أو شغّل: python app.py --port 8081' % port)
        sys.exit(1)
    ip = lan_ip()
    log('==============================================')
    log(' حارس العارضات يعمل%s' % (' (وضع تجريبي)' if args.demo else ''))
    log(' على هذا الكمبيوتر:  http://localhost:%d' % port)
    log(' من الموبايل (نفس الشبكة):  http://%s:%d' % (ip, port))
    log(' للإيقاف: اضغط Ctrl+C')
    log('==============================================')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log('تم الإيقاف')


if __name__ == '__main__':
    main()
