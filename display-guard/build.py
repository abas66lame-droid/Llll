# يبني haris.html (ملف واحد) من src/page.html + src/detector.js
import os
here = os.path.dirname(os.path.abspath(__file__))
page = open(os.path.join(here, 'src', 'page.html'), encoding='utf-8').read()
det = open(os.path.join(here, 'src', 'detector.js'), encoding='utf-8').read()
det = det[det.index('/* DETECTOR_START */'):det.index('/* DETECTOR_END */') + len('/* DETECTOR_END */')]
assert '/*__DETECTOR__*/' in page
open(os.path.join(here, 'haris.html'), 'w', encoding='utf-8').write(page.replace('/*__DETECTOR__*/', det))
# النسخة المبسّطة: نفس الملف بواجهة مختصرة
open(os.path.join(here, 'basit.html'), 'w', encoding='utf-8').write(page.replace('/*__DETECTOR__*/', det).replace('<script>', '<script>window.SIMPLE = true;</script>\n<script>', 1).replace('<title>حارس العارضات</title>', '<title>رقابة العارضة</title>'))
print('built haris.html + basit.html')
