# -*- coding: utf-8 -*-
p = r'F:\DeepSeek工作区\navwarn-map\tools\README.md'
s = open(p, encoding='utf-8').read()
i = s.find('## 十、')
assert i > 0
sec = open(r'F:\DeepSeek工作区\_navwarn_verify\sec10.md', encoding='utf-8').read()
out = s[:i] + sec
open(p, 'w', encoding='utf-8').write(out)
print('rewrote section 十; total chars', len(out), '| backspace', out.count(chr(8)), '| fences', out.count('```bash'))
