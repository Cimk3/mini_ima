import { mkdirSync, copyFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(desktop, 'dist', 'Miniima');
mkdirSync(output, { recursive: true });
copyFileSync(path.join(desktop, 'src-tauri', 'target', 'release', 'Miniima.exe'), path.join(output, 'Miniima.exe'));
copyFileSync(path.join(desktop, 'build', 'backend', 'miniima-backend.exe'), path.join(output, 'miniima-backend.exe'));
copyFileSync(path.join(desktop, 'README.md'), path.join(output, 'README.md'));
for (const document of ['VERIFICATION.md', 'DESIGN.md', 'design-qa.md']) {
  if (existsSync(path.join(desktop, document))) {
    copyFileSync(path.join(desktop, document), path.join(output, document));
  }
}
const evidence = path.join(desktop, 'build', 'history-review');
for (const name of ['results.json', 'desktop-conversation.png', 'desktop-dark-collapsed.png', 'desktop-980.png', 'phone-navigation.png']) {
  if (existsSync(path.join(evidence, name))) {
    const destination = path.join(output, 'verification');
    mkdirSync(destination, { recursive: true });
    copyFileSync(path.join(evidence, name), path.join(destination, name));
  }
}
console.log(`Desktop application: ${output}`);
