# -*- coding: utf-8 -*-
p = r'F:\DeepSeek工作区\navwarn-map\tools\README.md'
s = open(p, encoding='utf-8').read()
i = s.find('## 十、')
seg = s[i:i+90]
print([hex(ord(c)) for c in seg])
print(repr(seg))
k = s.find('ash', i)
print('ash at', k, 'context codes:', [hex(ord(c)) for c in s[k-8:k+6]])

import subprocess, json
node = r'C:\Users\x1503\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
js = r'''
const fs=require('fs');
const html=fs.readFileSync('F:/DeepSeek工作区/navwarn-map/index.html','utf8');
console.log('len', html.length);
const idx=html.indexOf('rocketcloud.js');
console.log('idx', idx, JSON.stringify(html.slice(idx-40, idx+30)));
console.log('has src=', html.includes('src="rocketcloud.js"'));
'''
open(r'F:\DeepSeek工作区\_navwarn_verify\_chk.js','w',encoding='utf-8').write(js)
print(subprocess.run([node, r'F:\DeepSeek工作区\_navwarn_verify\_chk.js'], capture_output=True, text=True, encoding='utf-8').stdout)
