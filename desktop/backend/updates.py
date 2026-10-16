"""Portable Windows updates from this project's public GitHub Releases only."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import struct
import tempfile
import threading
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from miniima.errors import MiniimaError

LATEST = 'https://api.github.com/repos/Cimk3/mini_ima/releases/latest'
FILES = ('Miniima.exe', 'miniima-backend.exe', 'README.md')
MAX_BYTES = 256 * 1024 * 1024
HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


class UpdateError(MiniimaError):
    pass


def version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value)
    if not match:
        raise UpdateError('版本格式无效，仅支持正式版本。')
    return tuple(map(int, match.groups()))


def checked_url(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != 'https' or url.hostname not in HOSTS or url.username or url.password or url.port not in (None, 443):
        raise UpdateError('更新服务器返回了不受支持的下载地址。')
    return value


def extract_package(archive: Path, destination: Path) -> dict[str, str]:
    """Reject extra files, traversal, links, duplicate entries and oversized archives."""
    expected = {f'Miniima/{name}': name for name in FILES}
    with zipfile.ZipFile(archive) as package:
        entries = [entry for entry in package.infolist() if not (entry.is_dir() and entry.filename == 'Miniima/')]
        if len(entries) != len(FILES) or {entry.filename for entry in entries} != set(expected):
            raise UpdateError('更新包文件清单不符合要求。')
        if sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise UpdateError('更新包解压后的大小超过限制。')
        hashes = {}
        for entry in entries:
            if entry.flag_bits & 1 or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise UpdateError('更新包包含加密文件或符号链接。')
            target = destination / expected[entry.filename]
            digest = hashlib.sha256()
            with package.open(entry) as source, target.open('xb') as output:
                while data := source.read(128 * 1024):
                    digest.update(data)
                    output.write(data)
            if target.suffix == '.exe':
                with target.open('rb') as binary:
                    header = binary.read(64)
                    if len(header) != 64 or header[:2] != b'MZ':
                        raise UpdateError('更新包中的程序格式无效。')
                    binary.seek(struct.unpack_from('<I', header, 60)[0])
                    if binary.read(6) != b'PE\0\0\x64\x86':
                        raise UpdateError('更新包不是 Windows x64 程序。')
            hashes[target.name] = digest.hexdigest()
        return hashes


class UpdateService:
    def __init__(self, client_factory=None):
        self.client_factory = client_factory or (lambda: httpx.Client(timeout=httpx.Timeout(20, connect=5),
            headers={'User-Agent': 'Mini-ima-updater', 'Accept': 'application/vnd.github+json'}, follow_redirects=False))
        self._lock = threading.Lock()
        self._download_lock = threading.Lock()
        self._progress = {'phase': 'idle', 'received': 0, 'total': 0}

    def status(self) -> dict:
        with self._lock:
            return dict(self._progress)

    def _progress_to(self, phase: str, received=0, total=0):
        with self._lock:
            self._progress = {'phase': phase, 'received': received, 'total': total}

    @staticmethod
    @contextmanager
    def response(client, url, *, timeout=10):
        for _ in range(6):
            checked_url(url)
            with client.stream('GET', url, timeout=timeout, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('location', ''))
                    continue
                if response.status_code in (403, 429):
                    raise UpdateError('更新服务暂时限制访问，请稍后重试。')
                if response.status_code == 404:
                    yield response
                    return
                if response.status_code != 200:
                    raise UpdateError('更新服务暂时不可用，请稍后重试。')
                yield response
                return
        raise UpdateError('更新下载重定向次数过多。')

    def _release(self, client, current: str) -> tuple[dict, dict | None]:
        current_numbers = version(current)
        with self.response(client, LATEST) as response:
            if response.status_code == 404:
                return {'current_version': current, 'latest_version': current, 'available': False}, None
            payload = bytearray()
            for data in response.iter_bytes():
                payload.extend(data)
                if len(payload) > 1024 * 1024:
                    raise UpdateError('更新服务响应过大。')
        release = json.loads(payload)
        tag = release.get('tag_name', '')
        latest_numbers = version(tag)
        available = latest_numbers > current_numbers and not release.get('draft') and not release.get('prerelease')
        latest = tag.removeprefix('v')
        result = {'current_version': current, 'latest_version': latest, 'available': bool(available),
                  'notes': str(release.get('body') or '')[:6000], 'downloadable': False}
        if not available:
            return result, None
        name = f'Mini-ima-{latest}-windows-x64.zip'
        asset = next((item for item in release.get('assets', []) if item.get('name') == name and item.get('state') == 'uploaded'), None)
        if asset is None or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', asset.get('digest') or ''):
            result['reason'] = '新版本尚未提供可校验的 Windows 更新包，请稍后重试。'
            return result, None
        expected_url = f'https://github.com/Cimk3/mini_ima/releases/download/{tag}/{name}'
        if asset.get('browser_download_url') != expected_url or type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_BYTES:
            raise UpdateError('新版本的更新包信息无效。')
        result.update(downloadable=True, size=asset['size'])
        return result, asset

    def check(self, current: str) -> dict:
        try:
            with self.client_factory() as client:
                return self._release(client, current)[0]
        except (httpx.HTTPError, ValueError, KeyError, AttributeError) as error:
            raise UpdateError('无法检查新版本，请检查网络后重试。') from error

    def prepare(self, current: str, app_dir: Path, expected_version: str | None = None) -> dict:
        if not self._download_lock.acquire(blocking=False):
            raise UpdateError('更新包正在下载，请等待完成。')
        stage = None
        self._progress_to('downloading')
        try:
            app_dir = app_dir.resolve(strict=True)
            if not all((app_dir / name).is_file() for name in FILES[:2]):
                raise UpdateError('应用目录不完整，无法更新。')
            try:
                stage = Path(tempfile.mkdtemp(prefix='.miniima-update-', dir=app_dir))
            except OSError as error:
                raise UpdateError('应用目录不可写，请将应用放到可写目录后重试。') from error
            with self.client_factory() as client:
                result, asset = self._release(client, current)
                if not asset:
                    raise UpdateError(result.get('reason', '当前已是最新版本。'))
                if expected_version is not None and result['latest_version'] != expected_version:
                    raise UpdateError('可用版本已变化，请重新检查并确认更新。')
                archive = stage / 'update.zip'
                digest, received, started = hashlib.sha256(), 0, time.monotonic()
                with self.response(client, asset['browser_download_url'], timeout=30) as response, archive.open('xb') as output:
                    if response.status_code != 200:
                        raise UpdateError('更新包暂时无法下载，请稍后重试。')
                    for data in response.iter_bytes(128 * 1024):
                        received += len(data)
                        if received > asset['size'] or time.monotonic() - started > 180:
                            raise UpdateError('更新包大小异常或下载超时，请重试。')
                        digest.update(data)
                        output.write(data)
                        self._progress_to('downloading', received, asset['size'])
                if received != asset['size'] or digest.hexdigest() != asset['digest'].split(':', 1)[1].lower():
                    raise UpdateError('更新包校验失败，已取消更新，请重新下载。')
                self._progress_to('verifying', received, received)
                hashes = extract_package(archive, stage)
                archive.unlink()
                token = secrets.token_hex(24)
                prepared = {'version': result['latest_version'], 'token': token, 'files': hashes}
                (stage / 'prepared.json').write_text(json.dumps(prepared), encoding='utf-8')
                self._progress_to('ready', received, received)
                return {'stage_dir': str(stage), 'version': prepared['version'], 'token': token}
        except Exception as error:
            if stage:
                shutil.rmtree(stage, ignore_errors=True)
            self._progress_to('error')
            if isinstance(error, UpdateError):
                raise
            raise UpdateError('下载或校验更新失败，当前程序未被修改，请重试。') from error
        finally:
            self._download_lock.release()
