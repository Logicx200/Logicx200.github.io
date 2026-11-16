const fs=require('node:fs'),path=require('node:path')
fs.writeFileSync(path.join(process.env.EXP_PROBE_DIR||'.','symprobe.txt'),
 'execPath='+process.execPath+'\nresourcesPath='+process.resourcesPath+'\n','utf8')
