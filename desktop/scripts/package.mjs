import { mkdirSync, copyFileSync, existsSync, mkdtempSync, readFileSync, writeFileSync, renameSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export function createPackage(desktopDirectory, { archive = true } = {}) {
  const desktop = path.resolve(desktopDirectory);
  const version = JSON.parse(readFileSync(path.join(desktop, 'package.json'), 'utf8')).version;
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Release version must be a stable semantic version.');
  const dist = path.join(desktop, 'dist');
  mkdirSync(dist, { recursive: true });
  const temp = mkdtempSync(path.join(dist, '.package-stage-'));
  const staged = path.join(temp, 'Miniima');
  const output = path.join(dist, 'Miniima');
  const zip = path.join(dist, `Mini-ima-${version}-windows-x64.zip`);
  const backup = path.join(temp, 'previous');
  let oldOutput = false, newOutput = false, oldZip = false, newZip = false;
  try {
    mkdirSync(staged);
    // This is the entire public file list; never copy existing output or developer evidence.
    copyFileSync(path.join(desktop, 'src-tauri', 'target', 'release', 'Miniima.exe'), path.join(staged, 'Miniima.exe'));
    copyFileSync(path.join(desktop, 'build', 'backend', 'miniima-backend.exe'), path.join(staged, 'miniima-backend.exe'));
    writeFileSync(path.join(staged, 'README.md'), readFileSync(path.join(desktop, 'RELEASE_README.md'), 'utf8').replaceAll('{{VERSION}}', version));
    if (archive) {
      const script = `import sys\nfrom pathlib import Path\nfrom zipfile import ZipFile, ZIP_DEFLATED\nroot = Path(sys.argv[1])\nwith ZipFile(sys.argv[2], 'w', ZIP_DEFLATED) as archive:\n    for name in ('Miniima.exe', 'miniima-backend.exe', 'README.md'):\n        archive.write(root / name, 'Miniima/' + name)\n`;
      const result = spawnSync(path.join(desktop, '.venv', 'Scripts', 'python.exe'), ['-c', script, staged, path.join(temp, 'release.zip')], { windowsHide: true, encoding: 'utf8' });
      if (result.error || result.status !== 0) throw new Error('无法生成发布压缩包。');
    }
    if (existsSync(output)) { renameSync(output, backup); oldOutput = true; }
    renameSync(staged, output); newOutput = true;
    if (archive) {
      if (existsSync(zip)) { renameSync(zip, path.join(temp, 'previous.zip')); oldZip = true; }
      renameSync(path.join(temp, 'release.zip'), zip); newZip = true;
    }
    return { output, archive: archive ? zip : null, version };
  } catch (error) {
    if (newOutput) rmSync(output, { recursive: true, force: true });
    if (oldOutput) renameSync(backup, output);
    if (newZip) rmSync(zip, { force: true });
    if (oldZip) renameSync(path.join(temp, 'previous.zip'), zip);
    throw error;
  } finally {
    // temp is a newly created child of this exact build output, never an input path.
    if (path.dirname(temp) === dist && path.basename(temp).startsWith('.package-stage-')) {
      try { rmSync(temp, { recursive: true, force: true, maxRetries: 2 }); }
      catch { console.warn('临时备份仍被占用，已保留在构建输出目录。'); }
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  console.log(createPackage(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')));
}
