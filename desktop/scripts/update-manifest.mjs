import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export function createUpdateManifest(desktopDirectory) {
  const desktop = path.resolve(desktopDirectory);
  const version = JSON.parse(readFileSync(path.join(desktop, 'package.json'), 'utf8')).version;
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Invalid release version.');
  const name = `Mini-ima-${version}-windows-x64.zip`;
  const archive = path.join(desktop, 'dist', name);
  const digest = 'sha256:' + createHash('sha256').update(readFileSync(archive)).digest('hex');
  const manifest = {
    tag_name: `v${version}`, draft: false, prerelease: false,
    body: readFileSync(path.join(desktop, 'RELEASE_README.md'), 'utf8').replaceAll('{{VERSION}}', version),
    assets: [{ name, state: 'uploaded', size: statSync(archive).size, digest,
      browser_download_url: `https://github.com/Cimk3/mini_ima/releases/download/v${version}/${name}` }],
  };
  const output = path.join(desktop, 'dist', 'miniima-update.json');
  writeFileSync(output, JSON.stringify(manifest, null, 2) + '\n');
  return output;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  console.log(createUpdateManifest(fileURLToPath(new URL('..', import.meta.url))));
}
