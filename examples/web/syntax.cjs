const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
for (const relative of fs.readdirSync('src', {recursive:true}).filter(name => /\.[cm]?js$/.test(name))) {
  const result = spawnSync(process.execPath, ['--check', path.join('src', relative)], {stdio:'inherit'});
  if (result.status !== 0) process.exit(result.status || 1);
}
console.log('All example JavaScript source files passed syntax validation');
