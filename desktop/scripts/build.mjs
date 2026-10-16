import { spawnSync } from 'node:child_process';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export function releaseEnvironment(environment = process.env) {
  const env = { ...environment };
  const flags = env.CARGO_ENCODED_RUSTFLAGS
    ? env.CARGO_ENCODED_RUSTFLAGS.split('\x1f')
    : (env.RUSTFLAGS?.trim().split(/\s+/).filter(Boolean) ?? []);
  // Rust embeds source locations in diagnostics; public binaries must not carry local user paths.
  for (const [source, destination] of [[homedir(), '/build/user'], [path.dirname(desktop), '/build/mini_ima']]) {
    for (const prefix of new Set([source, source.replaceAll('\\', '/'), path.toNamespacedPath(source)])) {
      flags.push(`--remap-path-prefix=${prefix}=${destination}`);
    }
  }
  env.CARGO_ENCODED_RUSTFLAGS = flags.join('\x1f');
  delete env.RUSTFLAGS;
  return env;
}

function run(script, args, env) {
  const result = spawnSync(process.execPath, [script, ...args], {
    cwd: desktop, env, stdio: 'inherit', windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Desktop build failed (${result.status ?? result.signal}).`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const env = releaseEnvironment();
    run(path.join(desktop, 'scripts', 'backend.mjs'), [], env);
    run(path.join(desktop, 'node_modules', '@tauri-apps', 'cli', 'tauri.js'), ['build', '--no-bundle'], env);
    run(path.join(desktop, 'scripts', 'package.mjs'), [], env);
    run(path.join(desktop, 'scripts', 'update-manifest.mjs'), [], env);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
