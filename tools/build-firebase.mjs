import { build } from 'esbuild';
import { readFileSync } from 'node:fs';
const v = JSON.parse(readFileSync(new URL('./node_modules/firebase/package.json', import.meta.url))).version;
await build({
  entryPoints: [new URL('./firebase-entry.js', import.meta.url).pathname],
  bundle: true, minify: true, format: 'iife', globalName: 'FB', target: ['es2020', 'safari15'],
  outfile: new URL('../display-cleaning/vendor/firebase.js', import.meta.url).pathname,
  banner: { js: `/* Firebase JS SDK ${v} — Apache-2.0 — bundled by tools/build-firebase.mjs */` },
  legalComments: 'none'
});
console.log('built firebase', v);
