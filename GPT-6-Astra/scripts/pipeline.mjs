import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const mode = process.argv[2] || 'rebuild';
const windowsBlender = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe';
const blender = process.env.BLENDER_PATH || (existsSync(windowsBlender) ? windowsBlender : 'blender');
const python = process.env.PYTHON || 'python';

function run(executable, args) {
  const result = spawnSync(executable, args, { cwd: root, stdio: 'inherit', shell: false });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}

const version = spawnSync(blender, ['--version'], { encoding: 'utf8', shell: false });
if (version.error || !/^Blender 5\.2\b/.test(version.stdout || '')) {
  console.error('Blender 5.2 is required. Set BLENDER_PATH to its executable.');
  process.exit(1);
}
if (mode === 'rebuild') {
  run(python, ['scripts/prepare_scene.py']);
  run(blender, ['--background', '--python-exit-code', '1', '--python', 'scripts/build_scene.py']);
}
if (!['rebuild', 'verify'].includes(mode)) throw new Error(`Unknown pipeline mode: ${mode}`);
run(blender, ['--background', 'blender/city.blend', '--python-exit-code', '1', '--python', 'scripts/validate_bake.py']);
run(python, ['scripts/compare_reference.py']);

