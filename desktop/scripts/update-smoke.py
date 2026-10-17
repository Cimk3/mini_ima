"""Windows update acceptance in fresh installations, using real programs and Mock downloads.

Run after desktop:build. Never opens a daily MINIIMA_HOME or modifies an input ZIP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import replace
from pathlib import Path

import httpx
from miniima.config import Settings, save_settings
from miniima.storage.repository import Repository

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP / 'backend'))
from updates import FILES, LATEST, UpdateService, extract_package

# Process operations are restricted to an exact executable under this newly created test root.
PROCESS_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($env:MINIIMA_SMOKE_ROOT).TrimEnd('\') + '\'
$install = [IO.Path]::GetFullPath($env:MINIIMA_SMOKE_INSTALL)
if (-not $install.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test installation' }
$exe = Join-Path $install 'Miniima.exe'
$apps = @(Get-Process -Name Miniima -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe })
if ($env:MINIIMA_SMOKE_ACTION -eq 'close') {
    foreach ($app in $apps) { [void]$app.CloseMainWindow() }
    foreach ($app in $apps) { Wait-Process -Id $app.Id -Timeout 10 -ErrorAction SilentlyContinue }
    $remaining = @($apps | Where-Object { -not $_.HasExited })
    foreach ($app in $remaining) { Stop-Process -Id $app.Id -ErrorAction SilentlyContinue }
    @{ forced = $remaining.Count } | ConvertTo-Json -Compress
} else {
    @($apps | ForEach-Object { @{ pid = $_.Id; window = ($_.MainWindowHandle -ne 0); version = $_.MainModule.FileVersionInfo.FileVersion } }) | ConvertTo-Json -Compress
}
'''


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def programs(install: Path) -> dict:
    return {name: digest(install / name) for name in FILES}


def data_snapshot(home: Path) -> tuple[str, str]:
    with sqlite3.connect(home / 'miniima.sqlite3') as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        contents = '\n'.join(connection.iterdump())
    return hashlib.sha256(contents.encode()).hexdigest(), digest(home / 'config.json')


def process_action(install: Path, env: dict, action='inspect'):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', PROCESS_SCRIPT],
        env={**env, 'MINIIMA_SMOKE_INSTALL': str(install), 'MINIIMA_SMOKE_ACTION': action},
        capture_output=True, text=True, encoding='utf-8', timeout=18,
        creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, 'Cannot inspect isolated Windows application processes.'
    return json.loads(result.stdout) if result.stdout.strip() else []


def wait_window(install: Path, env: dict) -> dict:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        apps = process_action(install, env)
        if isinstance(apps, dict):
            apps = [apps]
        ready = next((app for app in apps if app['window']), None)
        if ready:
            return ready
        time.sleep(0.25)
    raise AssertionError('The isolated restarted Windows application did not create a window.')


def prepared_update(install: Path, archive: Path, release_version: str) -> dict:
    payload = archive.read_bytes()
    name = f'Mini-ima-{release_version}-windows-x64.zip'
    url = f'https://github.com/Cimk3/mini_ima/releases/download/v{release_version}/{name}'
    release = {'tag_name': 'v' + release_version, 'assets': [{ 'name': name, 'state': 'uploaded',
        'size': len(payload), 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest(), 'browser_download_url': url }]}
    def handle(request):
        assert 'authorization' not in request.headers
        if str(request.url) == LATEST:
            return httpx.Response(200, json=release)
        assert str(request.url) == url
        return httpx.Response(200, content=payload)
    service = UpdateService(lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    return service.prepare('0.2.1', install, release_version)


def run_case(root: Path, label: str, old_archive: Path, new_archive: Path, release_version: str) -> dict:
    install = root / label
    install.mkdir()
    old_hashes = extract_package(old_archive, install)
    home = install / 'user-data'
    repository = Repository(home)
    repository.initialize()
    settings = replace(Settings(), api_key='mock-only', embedding_api_key='mock-only',
        base_url='http://127.0.0.1:9/v1', embedding_model='mock-embedding', embedding_dimension=8)
    save_settings(settings, home)
    kb = repository.create_kb('更新验收', settings)
    conversation = repository.save_answer(kb['id'], '本地验收问题', '本地验收回答', [])
    (install / 'keep.txt').write_text('unrelated file', encoding='utf-8')
    snapshot = data_snapshot(home)
    env = {name: value for name, value in os.environ.items() if not name.startswith('MINIIMA_')}
    env.update(MINIIMA_HOME=str(home), MINIIMA_SMOKE_ROOT=str(root), WEBVIEW2_USER_DATA_FOLDER=str(install / 'webview-profile'),
        HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9', ALL_PROXY='http://127.0.0.1:9')
    parent = subprocess.Popen([str(install / 'Miniima.exe')], cwd=install, env=env)
    helper = None
    try:
        initial = wait_window(install, env)
        prepared = prepared_update(install, new_archive, release_version)
        stage = Path(prepared['stage_dir'])
        expected_new = json.loads((stage / 'prepared.json').read_text())['files']
        if label == 'checksum_failure':
            (stage / 'README.md').write_text('tampered', encoding='utf-8')
        elif label == 'startup_failure':
            # Preserve valid staging checksums while deliberately causing Windows CreateProcess to fail.
            (stage / 'Miniima.exe').write_bytes(b'not a Windows executable')
            manifest = json.loads((stage / 'prepared.json').read_text())
            manifest['files']['Miniima.exe'] = digest(stage / 'Miniima.exe')
            (stage / 'prepared.json').write_text(json.dumps(manifest), encoding='utf-8')
        executable = stage / 'miniima-updater.exe'
        # Exercise the same helper mode shipped in 0.2.2, with a real old application parent.
        with zipfile.ZipFile(new_archive) as package:
            executable.write_bytes(package.read('Miniima/Miniima.exe'))
        helper = subprocess.Popen([str(executable), '--miniima-apply-update', str(parent.pid), str(install),
            str(stage), prepared['token'], prepared['version']], cwd=install, env=env)
        if label == 'checksum_failure':
            assert helper.wait(timeout=12) == 0
            assert not (stage / 'helper-ready').exists()
            assert parent.poll() is None and programs(install) == old_hashes
            restarted = initial
        else:
            deadline = time.monotonic() + 10
            while not (stage / 'helper-ready').exists() and time.monotonic() < deadline:
                assert helper.poll() is None, 'Native helper exited before the handoff.'
                time.sleep(0.05)
            assert (stage / 'helper-ready').exists()
            assert process_action(install, env, 'close')['forced'] == 0
            assert parent.wait(timeout=12) == 0
            assert helper.wait(timeout=25) == 0
            restarted = wait_window(install, env)
            assert restarted['pid'] != initial['pid']
            assert programs(install) == (expected_new if label == 'success' else old_hashes)
        assert process_action(install, env, 'close')['forced'] == 0
        assert data_snapshot(home) == snapshot
        assert repository.get_conversation(conversation)['messages'][0]['content'] == '本地验收问题'
        assert (install / 'keep.txt').read_text() == 'unrelated file'
        return {'case': label, 'passed': True, 'window_verified': True, 'restarted_version': restarted['version'],
            'database_unchanged': True, 'configuration_unchanged': True, 'unrelated_file_unchanged': True}
    finally:
        process_action(install, env, 'close')
        if helper is not None and helper.poll() is None:
            helper.terminate()
            helper.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-package', type=Path, default=DESKTOP / 'dist/Mini-ima-0.2.1-windows-x64.zip')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('This acceptance check requires Windows.')
    release_version = json.loads((DESKTOP / 'package.json').read_text())['version']
    new_archive = DESKTOP / f'dist/Mini-ima-{release_version}-windows-x64.zip'
    assert args.old_package.is_file() and new_archive.is_file(), 'Build the release and retain the previous public ZIP first.'
    root = Path(tempfile.mkdtemp(prefix='update-smoke-', dir=DESKTOP / 'build')).resolve()
    results = []
    for label in ['success', 'checksum_failure', 'startup_failure']:
        result = run_case(root, label, args.old_package.resolve(), new_archive, release_version)
        results.append(result)
        print(json.dumps(result), flush=True)
    report = {'version': release_version, 'archive_sha256': digest(new_archive),
        'network': 'MockTransport', 'model_api_calls': 0, 'cases': results}
    (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (DESKTOP / 'build/update-smoke-latest.txt').write_text(str(root), encoding='utf-8')
    print('PASS: isolated Windows update success, checksum rejection, startup rollback and data preservation', flush=True)


if __name__ == '__main__':
    main()
