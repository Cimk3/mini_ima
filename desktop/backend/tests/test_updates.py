import hashlib
import io
import json
import struct
import sys
import zipfile
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from updates import FILES, LATEST, RELEASE_MANIFEST, UpdateError, UpdateService, extract_package, version


def archive(extra=None):
    executable = bytearray(80)
    executable[:2] = b'MZ'
    struct.pack_into('<I', executable, 60, 64)
    executable[64:70] = b'PE\0\0\x64\x86'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as package:
        for name in FILES:
            package.writestr('Miniima/' + name, b'Instructions' if name.endswith('.md') else executable)
        if extra:
            package.writestr(extra, b'not allowed')
    return output.getvalue()


def service(payload, digest=None):
    download = 'https://github.com/Cimk3/mini_ima/releases/download/v0.3.0/Mini-ima-0.3.0-windows-x64.zip'
    release = {'tag_name': 'v0.3.0', 'draft': False, 'prerelease': False, 'body': 'A new release', 'assets': [{
        'name': 'Mini-ima-0.3.0-windows-x64.zip', 'state': 'uploaded', 'size': len(payload),
        'digest': digest or 'sha256:' + hashlib.sha256(payload).hexdigest(), 'browser_download_url': download}]}
    def handle(request):
        assert 'authorization' not in request.headers
        if str(request.url) == LATEST:
            return httpx.Response(200, json=release)
        assert str(request.url) == download
        return httpx.Response(200, content=payload)
    return UpdateService(lambda: httpx.Client(transport=httpx.MockTransport(handle)))


def test_mock_update_is_verified_and_staged_without_touching_current_programs(tmp_path):
    for name in FILES:
        (tmp_path / name).write_bytes(b'old')
    updater = service(archive())
    assert updater.check('0.2.0')['available']
    assert not updater.check('0.3.0')['available']
    assert not updater.check('0.4.0')['available']
    with pytest.raises(UpdateError, match='版本已变化'):
        updater.prepare('0.2.0', tmp_path, '0.2.1')
    prepared = updater.prepare('0.2.0', tmp_path, '0.3.0')
    stage = Path(prepared['stage_dir'])
    assert stage.parent == tmp_path
    manifest = json.loads((stage / 'prepared.json').read_text())
    assert set(manifest['files']) == set(FILES)
    assert manifest['token'] == prepared['token']
    assert all((tmp_path / name).read_bytes() == b'old' for name in FILES)
    assert updater.status()['phase'] == 'ready'


def test_bad_digest_cleans_stage_and_preserves_old_programs(tmp_path):
    for name in FILES:
        (tmp_path / name).write_bytes(b'old')
    updater = service(archive(), 'sha256:' + '0' * 64)
    with pytest.raises(UpdateError, match='校验失败'):
        updater.prepare('0.2.0', tmp_path)
    assert not list(tmp_path.glob('.miniima-update-*'))
    assert (tmp_path / 'Miniima.exe').read_bytes() == b'old'


@pytest.mark.parametrize('extra', ['../config.json', 'Miniima/config.json', 'Miniima/../Miniima.exe'])
def test_zip_rejects_extra_data_and_path_traversal(tmp_path, extra):
    path = tmp_path / 'package.zip'
    path.write_bytes(archive(extra))
    with pytest.raises(UpdateError, match='文件清单'):
        extract_package(path, tmp_path)
    assert not (tmp_path / 'Miniima.exe').exists()


def test_version_and_redirect_restrictions():
    assert version('v0.10.0') > version('0.2.9')
    with pytest.raises(UpdateError):
        version('0.3.0-beta.1')
    updater = UpdateService(lambda: httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(302, headers={'location': 'https://example.org/update.zip'}))))
    with pytest.raises(UpdateError, match='下载地址'):
        updater.check('0.2.0')


def fallback_service(api_status=403, *, fallback_status=200, digest=None):
    payload = archive()
    download = 'https://github.com/Cimk3/mini_ima/releases/download/v0.3.0/Mini-ima-0.3.0-windows-x64.zip'
    release = {'tag_name': 'v0.3.0', 'assets': [{
        'name': 'Mini-ima-0.3.0-windows-x64.zip', 'state': 'uploaded', 'size': len(payload),
        'digest': digest or 'sha256:' + hashlib.sha256(payload).hexdigest(), 'browser_download_url': download}]}
    requests = []
    def handle(request):
        assert 'authorization' not in request.headers
        url = str(request.url)
        requests.append(url)
        if url == LATEST:
            if api_status is None:
                raise httpx.ConnectError('API unavailable', request=request)
            return httpx.Response(api_status, headers={'retry-after': '120'})
        if url == RELEASE_MANIFEST:
            return httpx.Response(fallback_status, json=release)
        assert url == download
        return httpx.Response(200, content=payload)
    return UpdateService(lambda: httpx.Client(transport=httpx.MockTransport(handle))), requests


@pytest.mark.parametrize('status', [403, 429, 503, None])
def test_api_unavailable_uses_manifest_and_cached_checks_but_fresh_install_metadata(tmp_path, status):
    for name in FILES:
        (tmp_path / name).write_bytes(b'old')
    updater, requests = fallback_service(status)
    result = updater.check('0.2.0')
    assert result['available'] and result['downloadable']
    assert updater.check('0.2.0') == result
    prepared = updater.prepare('0.2.0', tmp_path, '0.3.0')
    assert Path(prepared['stage_dir']).joinpath('prepared.json').is_file()
    assert requests.count(LATEST) == 1
    assert requests.count(RELEASE_MANIFEST) == 2
    assert (tmp_path / 'Miniima.exe').read_bytes() == b'old'


def test_missing_fallback_does_not_report_up_to_date_or_repeatedly_hit_limited_api():
    updater, requests = fallback_service(fallback_status=404)
    for _ in range(2):
        with pytest.raises(UpdateError, match='限制访问'):
            updater.check('0.2.0')
    assert requests.count(LATEST) == 1


def test_manifest_fallback_keeps_checksum_verification(tmp_path):
    for name in FILES:
        (tmp_path / name).write_bytes(b'old')
    updater, _ = fallback_service(digest='sha256:' + '0' * 64)
    with pytest.raises(UpdateError, match='校验失败'):
        updater.prepare('0.2.0', tmp_path, '0.3.0')
    assert not list(tmp_path.glob('.miniima-update-*'))
    assert (tmp_path / 'Miniima.exe').read_bytes() == b'old'
