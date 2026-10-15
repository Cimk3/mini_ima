import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, copyFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.dirname(desktop);
const python = path.join(desktop, '.venv', 'Scripts', 'python.exe');
const temp = path.join(desktop, 'build', 'temp');
mkdirSync(temp, { recursive: true });
if (!existsSync(python)) throw new Error('先按 desktop/README.md 创建 desktop/.venv。');
const env = { ...process.env, TEMP: temp, TMP: temp, CMAKE_GENERATOR: 'Visual Studio 17 2022',
  PATH: `${path.dirname(python)};${process.env.PATH}`, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' };
function run(command, args) {
  const result = spawnSync(command, args, { cwd: desktop, env, stdio: 'inherit', windowsHide: true });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
const wheels = path.join(desktop, 'build', 'core-wheels');
mkdirSync(wheels, { recursive: true });
const coreBuild = path.join(desktop, 'build', 'core', '{wheel_tag}');
run(python, ['-m', 'pip', 'wheel', '--no-build-isolation', '--no-deps',
  '--config-settings', `build-dir=${coreBuild}`, root, '--wheel-dir', wheels]);
const wheel = readdirSync(wheels).find(name => name.startsWith('miniima-') && name.endsWith('.whl'));
if (!wheel) throw new Error('Core wheel not found');
run(python, ['-m', 'pip', 'install', path.join(wheels, wheel)]);
run(python, ['-m', 'pip', 'install', '--force-reinstall', '--no-deps', path.join(wheels, wheel)]);
run(python, ['-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console',
  '--name', 'miniima-backend', '--distpath', 'build/backend', '--workpath', 'build/pyinstaller',
  '--specpath', 'build', '--collect-all', 'miniima', '--collect-data', 'certifi',
  '--hidden-import', 'miniima._exact', '--exclude-module', 'pytest', 'backend/worker.py']);
const binaries = path.join(desktop, 'src-tauri', 'binaries');
mkdirSync(binaries, { recursive: true });
copyFileSync(path.join(desktop, 'build', 'backend', 'miniima-backend.exe'),
  path.join(binaries, 'miniima-backend-x86_64-pc-windows-msvc.exe'));
console.log('Windows sidecar prepared.');
