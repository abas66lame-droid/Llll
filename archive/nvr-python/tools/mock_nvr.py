# أداة للمطورين: محاكي NVR هكفيجن (مصادقة Digest) لاختبار النظام بدون جهاز حقيقي.
# التشغيل: python tools/mock_nvr.py 8099  ثم أضف NVR بالعنوان 127.0.0.1 والمنفذ 8099 والمستخدم admin وكلمة السر Pass1234
# محاكي NVR هكفيجن مع مصادقة Digest للاختبار
import hashlib, io, os, re, sys, time, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..'))
import demo as DM
USER, PW, REALM = 'admin', 'Pass1234', 'DS-7616NI'
NONCE = uuid.uuid4().hex
scenes = {1: DM.DemoScene(11), 2: DM.DemoScene(12)}
md5 = lambda s: hashlib.md5(s.encode()).hexdigest()
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def auth(self):
        a = self.headers.get('Authorization', '')
        if not a.startswith('Digest '):
            return False
        f = dict(re.findall(r'(\w+)="?([^",]+)"?', a[7:]))
        ha1 = md5('%s:%s:%s' % (USER, REALM, PW)); ha2 = md5('GET:%s' % f.get('uri', ''))
        exp = md5('%s:%s:%s:%s:%s:%s' % (ha1, f.get('nonce'), f.get('nc'), f.get('cnonce'), f.get('qop'), ha2)) if f.get('qop') else md5('%s:%s:%s' % (ha1, f.get('nonce'), ha2))
        return f.get('username') == USER and f.get('response') == exp
    def do_GET(self):
        if not self.auth():
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Digest qop="auth", realm="%s", nonce="%s", stale="FALSE"' % (REALM, NONCE))
            self.send_header('Content-Length', '0'); self.end_headers(); return
        p = self.path.split('?')[0]
        ns = 'xmlns="http://www.hikvision.com/ver20/XMLSchema"'
        if p == '/ISAPI/System/deviceInfo':
            b = ('<?xml version="1.0"?><DeviceInfo %s><deviceName>NVR Mansour</deviceName><model>DS-7616NI-K2</model><serialNumber>DS123</serialNumber><firmwareVersion>V4.71.010</firmwareVersion><deviceType>NVR</deviceType></DeviceInfo>' % ns).encode()
            return self.ok(b, 'application/xml')
        if p == '/ISAPI/ContentMgmt/InputProxy/channels':
            b = ('<?xml version="1.0"?><InputProxyChannelList %s><InputProxyChannel><id>1</id><name>Phones Wall</name></InputProxyChannel><InputProxyChannel><id>2</id><name>Laptops</name></InputProxyChannel></InputProxyChannelList>' % ns).encode()
            return self.ok(b, 'application/xml')
        m = re.match(r'/ISAPI/Streaming/channels/(\d+)/picture', p)
        if m:
            ch = int(m.group(1)) // 100
            if ch not in scenes:
                self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
            sc = scenes[ch]
            ctl = __import__('os').path.join(__import__('tempfile').gettempdir(), 'nvr_ctl_%d') % ch
            if os.path.exists(ctl):
                sc.present = [c == '1' for c in open(ctl).read().strip()]
            buf = io.BytesIO(); sc.render().save(buf, 'JPEG', quality=85)
            return self.ok(buf.getvalue(), 'image/jpeg')
        self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers()
    def ok(self, b, ct):
        self.send_response(200); self.send_header('Content-Type', ct); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1]) if len(sys.argv) > 1 else 8099), H).serve_forever()
