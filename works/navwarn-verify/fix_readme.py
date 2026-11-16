# -*- coding: utf-8 -*-
import io
p = r'F:\DeepSeek工作区\navwarn-map\tools\README.md'
s = open(p, encoding='utf-8').read()
bad = chr(96) + chr(8) + 'ash'
good = chr(96) * 3 + 'bash'
print('bad occurrences:', s.count(bad), '| backspace:', s.count(chr(8)))
s = s.replace(bad, good)
s = s.replace(chr(8), '')
open(p, 'w', encoding='utf-8').write(s)
s2 = open(p, encoding='utf-8').read()
print('after: backspace', s2.count(chr(8)), '| fences', s2.count('```bash'))
i = s2.find('## 十、')
print(repr(s2[i:i+120]))
