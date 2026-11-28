# يبني haris.html (ملف واحد) من src/page.html + src/detector.js
import os
here = os.path.dirname(os.path.abspath(__file__))
page = open(os.path.join(here, 'src', 'page.html'), encoding='utf-8').read()
det = open(os.path.join(here, 'src', 'detector.js'), encoding='utf-8').read()
det = det[det.index('/* DETECTOR_START */'):det.index('/* DETECTOR_END */') + len('/* DETECTOR_END */')]
assert '/*__DETECTOR__*/' in page
# نموذج حركة الإخفاء المدرَّب (MNNIT Shoplifting 2022، CC BY 4.0) يُضمَّن في الملف
cm = os.path.join(here, 'src', 'models', 'conceal_model.json')
ra = os.path.join(here, 'src', 'models', 'ra_filter.json')
page = page.replace('/*__RA_MODEL__*/null', open(ra, encoding='utf-8').read().strip() if os.path.exists(ra) else 'null')
rv = os.path.join(here, 'src', 'models', 'ra_vision.json')
page = page.replace('/*__RA_VIS__*/null', open(rv, encoding='utf-8').read().strip() if os.path.exists(rv) else 'null')
page = page.replace('/*__CONCEAL_MODEL__*/null', open(cm, encoding='utf-8').read().strip() if os.path.exists(cm) else 'null')
open(os.path.join(here, 'haris.html'), 'w', encoding='utf-8').write(page.replace('/*__DETECTOR__*/', det))
# النسخة المبسّطة: نفس الملف بواجهة مختصرة
open(os.path.join(here, 'basit.html'), 'w', encoding='utf-8').write(page.replace('/*__DETECTOR__*/', det).replace('<script>', '<script>window.SIMPLE = true;</script>\n<script>', 1).replace('<title>حارس العارضات</title>', '<title>رقابة العارضة</title>'))
print('built haris.html + basit.html')
