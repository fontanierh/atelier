// Bundles the board app into the server's static assets. The output is committed, so `atelier board serve` needs no Node.
// `--check` builds in memory and fails if the committed bundle is not what the sources build.
import {readFile} from 'node:fs/promises';
import * as esbuild from 'esbuild';

const options = {
  entryPoints: {app: 'src/main.tsx'},
  outdir: '../../../studio/atelier/board_web_assets',
  bundle: true,
  format: 'iife',
  target: ['es2022', 'safari16'],
  minify: true,
  sourcemap: false,
  legalComments: 'none',
  define: {'process.env.NODE_ENV': '"production"'},
  logLevel: 'info',
};

if (process.argv.includes('--watch')) await (await esbuild.context(options)).watch();
else if (process.argv.includes('--check')) {
  const {outputFiles} = await esbuild.build({...options, write: false, logLevel: 'warning'});
  for (const file of outputFiles) {
    if (await readFile(file.path, 'utf8').catch(() => '') !== file.text) {
      console.error(`${file.path} is out of date: run npm run build`); process.exit(1);
    }
  }
} else await esbuild.build(options);
