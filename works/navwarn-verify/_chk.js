
const fs=require('fs');
const html=fs.readFileSync('F:/DeepSeek工作区/navwarn-map/index.html','utf8');
console.log('len', html.length);
const idx=html.indexOf('rocketcloud.js');
console.log('idx', idx, JSON.stringify(html.slice(idx-40, idx+30)));
console.log('has src=', html.includes('src="rocketcloud.js"'));
