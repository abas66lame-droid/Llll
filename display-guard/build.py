# يبني haris.html (ملف واحد) من src/page.html + src/detector.js
import os
here = os.path.dirname(os.path.abspath(__file__))
page = open(os.path.join(here, 'src', 'page.html'), encoding='utf-8').read()
det = open(os.path.join(here, 'src', 'detector.js'), encoding='utf-8').read()
det = det[det.index('/* DETECTOR_START */'):det.index('/* DETECTOR_END */') + len('/* DETECTOR_END */')]
assert '/*__DETECTOR__*/' in page
open(os.path.join(here, 'haris.html'), 'w', encoding='utf-8').write(page.replace('/*__DETECTOR__*/', det))
print('built haris.html')
