from __future__ import annotations

import shutil
import uuid

from miniima.errors import MiniimaError
from miniima.storage.repository import Repository


class TrashService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def _clean_originals(self, kb: dict) -> None:
        uuid.UUID(kb['id'])
        home = self.repository.home.resolve()
        root = home / 'originals'
        directory = root / kb['id']
        if root.is_symlink() or root.is_junction() or root.resolve().parent != home:
            raise MiniimaError('原文目录路径异常，未执行清理。')
        if directory.is_symlink() or directory.is_junction() or directory.resolve().parent != root.resolve():
            raise MiniimaError('原文目录路径异常，未执行清理。')
        if directory.exists():
            shutil.rmtree(directory)

    def purge(self, kind: str, identifier: str) -> None:
        self.repository.purge(kind, identifier, self._clean_originals if kind == 'kb' else None)

    def empty(self) -> None:
        items = self.repository.list_trash()
        # Delete independently trashed children before their parent cascades.
        for item in sorted(items, key=lambda item: item['kind'] == 'kb'):
            self.purge(item['kind'], item['id'])
