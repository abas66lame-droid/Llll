# -*- coding: utf-8 -*-
"""
مصادر الصور:
  - Hikvision: سحب لقطة من الـ NVR أو الكاميرا عبر ISAPI (مصادقة Digest/Basic)
  - Folder: أحدث صورة في مجلد (لأي كاميرا أخرى ترفع لقطات عبر FTP، أو لتجربة صور الموبايل)
  - Demo: كاميرا افتراضية (demo.py)
"""
import io
import os
import ssl
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from PIL import Image


def _strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and '}' in el.tag:
            el.tag = el.tag.split('}', 1)[1]
    return root


class HikvisionClient:
    def __init__(self, host, port=80, user='admin', password='', https=False, timeout=8):
        scheme = 'https' if https else 'http'
        self.base = '%s://%s:%s' % (scheme, host.strip(), int(port or (443 if https else 80)))
        pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        pm.add_password(None, self.base, user, password)
        handlers = [urllib.request.HTTPDigestAuthHandler(pm), urllib.request.HTTPBasicAuthHandler(pm)]
        if https:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE   # أجهزة الـ NVR تستخدم شهادات ذاتية التوقيع
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        self.opener = urllib.request.build_opener(*handlers)
        self.timeout = timeout
        self._snap_path = {}

    def get(self, path):
        try:
            with self.opener.open(self.base + path, timeout=self.timeout) as r:
                return r.read(), r.headers.get('Content-Type', '')
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError('اسم المستخدم أو كلمة السر غير صحيحة (401)')
            if e.code == 403:
                raise RuntimeError('المستخدم لا يملك صلاحية (403)')
            if e.code == 404:
                raise RuntimeError('الخاصية غير مدعومة في هذا الجهاز (404)')
            raise RuntimeError('خطأ من الجهاز: %s' % e.code)
        except urllib.error.URLError as e:
            raise RuntimeError('تعذّر الوصول إلى الجهاز: %s' % getattr(e, 'reason', e))
        except OSError as e:
            raise RuntimeError('تعذّر الاتصال: %s' % e)

    def xml(self, path):
        data, _ = self.get(path)
        return _strip_ns(ET.fromstring(data))

    def device_info(self):
        r = self.xml('/ISAPI/System/deviceInfo')
        g = lambda k: (r.findtext(k) or '').strip()
        return {'name': g('deviceName'), 'model': g('model'), 'serial': g('serialNumber'), 'firmware': g('firmwareVersion'), 'type': g('deviceType')}

    def channels(self):
        """قائمة الكاميرات المربوطة بالـ NVR (أو قناة واحدة للكاميرا المنفردة)."""
        out = []
        try:
            r = self.xml('/ISAPI/ContentMgmt/InputProxy/channels')
            for c in r.iter('InputProxyChannel'):
                cid = (c.findtext('id') or '').strip()
                if cid.isdigit():
                    out.append({'channel': int(cid), 'name': (c.findtext('name') or ('Camera %s' % cid)).strip()})
        except Exception:
            pass
        if not out:
            try:
                r = self.xml('/ISAPI/Streaming/channels')
                seen = set()
                for c in r.iter('StreamingChannel'):
                    cid = (c.findtext('id') or '').strip()
                    if cid.isdigit() and int(cid) >= 100:
                        ch = int(cid) // 100
                        if ch not in seen:
                            seen.add(ch)
                            out.append({'channel': ch, 'name': (c.findtext('channelName') or ('Camera %d' % ch)).strip()})
            except Exception:
                pass
        return sorted(out, key=lambda c: c['channel'])

    def snapshot(self, channel, stream=1):
        sid = '%d0%d' % (int(channel), int(stream))
        paths = ['/ISAPI/Streaming/channels/%s/picture' % sid,
                 '/ISAPI/ContentMgmt/StreamingProxy/channels/%s/picture' % sid,
                 '/ISAPI/Streaming/channels/%s/picture?snapShotImageType=JPEG' % sid]
        known = self._snap_path.get(sid)
        if known:
            paths = [known] + [p for p in paths if p != known]
        last = None
        for p in paths:
            try:
                data, ct = self.get(p)
                if data[:2] == b'\xff\xd8' or 'image' in ct:
                    self._snap_path[sid] = p
                    img = Image.open(io.BytesIO(data))
                    img.load()
                    return img
                last = RuntimeError('الجهاز لم يُرجع صورة')
            except Exception as e:
                last = e
                if 'كلمة السر' in str(e):
                    break
        raise last or RuntimeError('تعذّر سحب الصورة')


class HikvisionSource:
    def __init__(self, client, channel, stream=1):
        self.client, self.channel, self.stream = client, channel, stream

    def fetch(self):
        return self.client.snapshot(self.channel, self.stream)


class FolderSource:
    EXT = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')

    def __init__(self, path):
        self.path = path

    def fetch(self):
        if not os.path.isdir(self.path):
            raise RuntimeError('المجلد غير موجود: %s' % self.path)
        files = [os.path.join(self.path, f) for f in os.listdir(self.path) if f.lower().endswith(self.EXT)]
        if not files:
            raise RuntimeError('لا توجد صور في المجلد')
        f = max(files, key=os.path.getmtime)
        img = Image.open(f)
        img.load()
        return img.convert('RGB')
