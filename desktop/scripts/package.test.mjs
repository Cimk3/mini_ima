import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createPackage } from './package.mjs';
import { createUpdateManifest } from './update-manifest.mjs';
import { createHash } from 'node:crypto';

function fixture() {
  const base = fileURLToPath(new URL('../build/package-tests/', import.meta.url));
  mkdirSync(base, { recursive: true });
  const root = mkdtempSync(path.join(base, 'run-'));
  for (const folder of ['src-tauri/target/release', 'build/backend', 'dist/Miniima/verification']) mkdirSync(path.join(root, folder), { recursive: true });
  writeFileSync(path.join(root, 'package.json'), JSON.stringify({ version: '0.2.0' }));
  writeFileSync(path.join(root, 'src-tauri/target/release/Miniima.exe'), 'new desktop');
  writeFileSync(path.join(root, 'build/backend/miniima-backend.exe'), 'new backend');
  writeFileSync(path.join(root, 'RELEASE_README.md'), readFileSync(new URL('../RELEASE_README.md', import.meta.url)));
  writeFileSync(path.join(root, 'dist/Miniima/old.log'), 'old log');
  writeFileSync(path.join(root, 'dist/Miniima/verification/outdated.png'), 'old evidence');
  return root;
}

test('clean package only contains the public file list and versioned absolute links', () => {
  const root = fixture();
  try {
    const result = createPackage(root, { archive: false });
    assert.deepEqual(readdirSync(result.output).sort(), ['Miniima.exe', 'README.md', 'miniima-backend.exe'].sort());
    const readme = readFileSync(path.join(result.output, 'README.md'), 'utf8');
    assert.ok(readme.includes('Mini-ima 0.2.0'));
    assert.ok(!readme.includes('{{VERSION}}'));
    assert.ok([...readme.matchAll(/\]\(([^)]+)\)/g)].every(match => match[1].startsWith('https://github.com/Cimk3/mini_ima/blob/v0.2.0/')));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('missing build input leaves the previous application directory untouched', () => {
  const root = fixture();
  try {
    rmSync(path.join(root, 'build/backend/miniima-backend.exe'));
    assert.throws(() => createPackage(root, { archive: false }));
    assert.equal(readFileSync(path.join(root, 'dist/Miniima/old.log'), 'utf8'), 'old log');
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('public update manifest matches the exact archive and fixed release URL', () => {
  const root = fixture();
  try {
    const payload = Buffer.from('an isolated test archive');
    writeFileSync(path.join(root, 'dist/Mini-ima-0.2.0-windows-x64.zip'), payload);
    const manifest = JSON.parse(readFileSync(createUpdateManifest(root), 'utf8'));
    assert.equal(manifest.tag_name, 'v0.2.0');
    assert.equal(manifest.assets[0].size, payload.length);
    assert.equal(manifest.assets[0].digest, 'sha256:' + createHash('sha256').update(payload).digest('hex'));
    assert.equal(manifest.assets[0].browser_download_url,
      'https://github.com/Cimk3/mini_ima/releases/download/v0.2.0/Mini-ima-0.2.0-windows-x64.zip');
    assert.ok(!manifest.body.includes('{{VERSION}}'));
  } finally { rmSync(root, { recursive: true, force: true }); }
});
