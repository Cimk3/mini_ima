from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

import numpy as np

from miniima.config import Settings, save_settings
from miniima.errors import MiniimaError

SCHEMA_VERSION = 3

def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, home: Path):
        self.home = home
        self.path = home / "miniima.sqlite3"

    @contextmanager
    def connection(self):
        if not self.path.exists():
            raise MiniimaError("尚未初始化，请先运行 miniima init。")
        connection = sqlite3.connect(self.path, timeout=15)
        if connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
            connection.close()
            self.initialize()
            connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "originals").mkdir(exist_ok=True)
        if not (self.home / "config.json").exists():
            save_settings(Settings(), self.home)
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            old_version = connection.execute('PRAGMA user_version').fetchone()[0]
            if 0 < old_version < SCHEMA_VERSION:
                backups = self.home / 'backups'
                backups.mkdir(exist_ok=True)
                backup = backups / f'miniima-v{old_version}-{uuid.uuid4().hex}.sqlite3'
                with sqlite3.connect(backup) as destination:
                    connection.backup(destination)
            # Serialize migrations, including repeated/concurrent init, in one transaction.
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            migrations = sorted(files("miniima.storage").joinpath("migrations").iterdir(), key=lambda p: p.name)
            latest = max(int(item.name.split("_", 1)[0]) for item in migrations if item.name.endswith(".sql"))
            if version > latest:
                raise MiniimaError("数据库版本高于此程序支持的版本，请升级程序。")
            for migration in migrations:
                if not migration.name.endswith(".sql"):
                    continue
                number = int(migration.name.split("_", 1)[0])
                if number <= version:
                    continue
                # Avoid executescript, which would implicitly commit the surrounding transaction.
                statement = ""
                for line in migration.read_text(encoding="utf-8").splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        connection.execute(statement)
                        statement = ""
                if statement.strip():
                    raise MiniimaError("Schema 迁移文件包含不完整 SQL。")
                connection.execute("INSERT INTO schema_migrations VALUES (?, ?)", (number, now()))
                connection.execute(f"PRAGMA user_version = {number}")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_kb(self, name: str, settings: Settings) -> dict:
        name = name.strip()
        if not name:
            raise MiniimaError("知识库名称不能为空。")
        if re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", name):
            raise MiniimaError("知识库名称不能使用 UUID，以免与知识库 ID 混淆。")
        if not settings.embedding_model or settings.embedding_dimension < 1:
            raise MiniimaError("创建知识库前请配置向量模型及其维度。")
        identifier, timestamp = str(uuid.uuid4()), now()
        try:
            with self.connection() as connection, connection:
                connection.execute("""INSERT INTO knowledge_bases
                    (id,name,embedding_model,embedding_dimension,embedding_base_url,created_at,updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""", (
                    identifier, name, settings.embedding_model, settings.embedding_dimension,
                    settings.embedding_url, timestamp, timestamp))
        except sqlite3.IntegrityError as exc:
            with self.connection() as connection:
                deleted = connection.execute('SELECT id FROM knowledge_bases WHERE name=? AND deleted_at IS NOT NULL', (name,)).fetchone()
            if deleted:
                raise MiniimaError('同名知识库在回收站中，请先恢复或彻底删除。') from exc
            raise MiniimaError("同名知识库已经存在，请使用其他名称。") from exc
        return self.get_kb(identifier)

    def get_kb(self, reference: str, *, include_deleted: bool = False) -> dict:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM knowledge_bases WHERE (id = ? OR name = ?) AND (? OR deleted_at IS NULL)",
                                      (reference, reference, include_deleted)).fetchall()
        if not rows:
            raise MiniimaError("找不到指定知识库。")
        if len(rows) != 1:
            raise MiniimaError("知识库名称与 ID 存在歧义，请使用 UUID。")
        return dict(rows[0])

    def list_kbs(self) -> list[dict]:
        with self.connection() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM knowledge_bases WHERE deleted_at IS NULL ORDER BY created_at, id")]

    def delete_kb(self, reference: str) -> dict:
        kb = self.get_kb(reference, include_deleted=True)
        with self.connection() as connection, connection:
            connection.execute("UPDATE knowledge_bases SET deleted_at=COALESCE(deleted_at,?) WHERE id=?", (now(), kb['id']))
        return kb

    def find_document(self, kb_id: str, digest: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM documents WHERE knowledge_base_id = ? AND sha256 = ?",
                                     (kb_id, digest)).fetchone()
        return dict(row) if row else None

    def record_failure(self, document: dict, message: str) -> None:
        timestamp = now()
        with self.connection() as connection, connection:
            connection.execute("""INSERT INTO documents
                (id, knowledge_base_id, filename, sha256, source_type, status, error, created_at, updated_at)
                VALUES (:id, :knowledge_base_id, :filename, :sha256, :source_type, 'failed', :error, :time, :time)
                ON CONFLICT(knowledge_base_id, sha256) DO UPDATE SET
                    status = 'failed', error = excluded.error, updated_at = excluded.updated_at
                    WHERE documents.status != 'ready'""", {**document, "error": message, "time": timestamp})

    def store_document(self, document: dict, chunks, vectors: np.ndarray, kb: dict) -> bool:
        timestamp = now()
        with self.connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT status FROM documents WHERE knowledge_base_id=? AND sha256=?",
                                          (kb["id"], document["sha256"])).fetchone()
            if existing and existing["status"] == "ready":
                return False
            connection.execute("""INSERT INTO documents VALUES
                (:id, :knowledge_base_id, :filename, :sha256, :source_type, :original_path, 'ready', NULL, :time, :time)
                ON CONFLICT(knowledge_base_id, sha256) DO UPDATE SET
                    filename=excluded.filename, source_type=excluded.source_type,
                    original_path=excluded.original_path, status='ready',
                    error=NULL, updated_at=excluded.updated_at""", {**document, "time": timestamp})
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (document["id"],))
            for chunk, vector in zip(chunks, vectors, strict=True):
                cursor = connection.execute("""INSERT INTO chunks
                    (uuid, document_id, content, chunk_index, source_type, source_metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
                        chunk.chunk_id, document["id"], chunk.content, chunk.chunk_index, chunk.source_type,
                        json.dumps(chunk.source_metadata, ensure_ascii=False), timestamp, timestamp))
                connection.execute("INSERT INTO embeddings VALUES (?, ?, ?, ?, ?, ?)", (
                    cursor.lastrowid, kb["embedding_model"], kb["embedding_dimension"],
                    np.asarray(vector, dtype="<f4").tobytes(), timestamp, timestamp))

            connection.execute("UPDATE knowledge_bases SET updated_at = ? WHERE id = ?", (timestamp, kb["id"]))
        return True

    def index_data(self, kb: dict) -> tuple[list[int], np.ndarray]:
        self.get_kb(kb['id'])
        with self.connection() as connection:
            rows = connection.execute("""SELECT e.chunk_id, e.model, e.dimension, e.vector
                FROM embeddings e JOIN chunks c ON e.chunk_id=c.id JOIN documents d ON c.document_id=d.id
                WHERE d.knowledge_base_id=? AND d.status='ready' ORDER BY e.chunk_id""", (kb["id"],)).fetchall()
        vectors = []
        for row in rows:
            if row["model"] != kb["embedding_model"] or row["dimension"] != kb["embedding_dimension"]:
                raise MiniimaError("数据库中存在不兼容向量，请检查知识库。")
            vector = np.frombuffer(row["vector"], dtype="<f4")
            if len(vector) != kb["embedding_dimension"]:
                raise MiniimaError("数据库中的向量长度异常。")
            vectors.append(vector)
        matrix = np.stack(vectors) if vectors else np.empty((0, kb["embedding_dimension"]), dtype=np.float32)
        return [row["chunk_id"] for row in rows], matrix

    def get_chunks(self, kb_id: str, chunk_ids: list[int]) -> dict[int, dict]:
        self.get_kb(kb_id)
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        with self.connection() as connection:
            rows = connection.execute(f"""SELECT c.*, d.filename, d.knowledge_base_id
                FROM chunks c JOIN documents d ON c.document_id=d.id
                WHERE d.knowledge_base_id=? AND d.status='ready' AND c.id IN ({placeholders})""",
                                      (kb_id, *chunk_ids)).fetchall()
        return {row["id"]: {**dict(row), "source_metadata": json.loads(row["source_metadata"])} for row in rows}

    def list_documents(self, reference: str) -> list[dict]:
        kb = self.get_kb(reference)
        with self.connection() as connection:
            return [dict(row) for row in connection.execute("""SELECT d.*, COUNT(c.id) AS chunk_count
                FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
                WHERE d.knowledge_base_id=? GROUP BY d.id ORDER BY d.created_at, d.id""", (kb["id"],))]

    def document_excerpt(self, reference: str, document_id: str) -> dict | None:
        kb = self.get_kb(reference)
        with self.connection() as connection:
            row = connection.execute("""SELECT c.*, d.filename FROM chunks c
                JOIN documents d ON c.document_id=d.id
                WHERE d.knowledge_base_id=? AND d.id=? AND d.status='ready'
                ORDER BY c.chunk_index LIMIT 1""", (kb["id"], document_id)).fetchone()
        return {**dict(row), "source_metadata": json.loads(row["source_metadata"])} if row else None

    def save_answer(self, kb_id: str, question: str, answer: str, citations: list[dict]) -> str:
        conversation_id, user_id, answer_id = (str(uuid.uuid4()) for _ in range(3))
        timestamp = now()
        with self.connection() as connection, connection:
            self._active_kb(connection, kb_id)
            connection.execute("INSERT INTO conversations (id,knowledge_base_id,created_at,updated_at,title) VALUES (?,?,?,?,?)",
                               (conversation_id, kb_id, timestamp, timestamp, question[:30]))
            connection.executemany("""INSERT INTO messages
                (id,conversation_id,role,content,created_at,updated_at,position,reply_to) VALUES (?,?,?,?,?,?,?,?)""", [
                (user_id, conversation_id, "user", question, timestamp, timestamp, 0, None),
                (answer_id, conversation_id, "assistant", answer, timestamp, timestamp, 1, user_id)])
            for citation in citations:
                connection.execute("INSERT INTO message_citations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    str(uuid.uuid4()), answer_id, citation["id"], citation["citation_number"],
                    citation["document_id"], citation["filename"], citation["content"],
                    json.dumps(citation["source_metadata"], ensure_ascii=False), timestamp))
        return conversation_id

    @staticmethod
    def _active_kb(connection, kb_id: str) -> None:
        if not connection.execute('SELECT id FROM knowledge_bases WHERE id=? AND deleted_at IS NULL', (kb_id,)).fetchone():
            raise MiniimaError('知识库不存在或已移入回收站。')

    @staticmethod
    def _conversation(connection, identifier: str) -> dict:
        row = connection.execute('''SELECT c.*, k.name AS knowledge_base_name FROM conversations c
            JOIN knowledge_bases k ON k.id=c.knowledge_base_id
            WHERE c.id=? AND c.deleted_at IS NULL AND k.deleted_at IS NULL''', (identifier,)).fetchone()
        if not row:
            raise MiniimaError('对话不存在或已移入回收站。')
        return dict(row)

    def list_conversations(self, offset: int = 0, limit: int = 50, query: str = '') -> dict:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise MiniimaError('对话分页参数无效。')
        if not isinstance(query, str) or len(query) > 200:
            raise MiniimaError('搜索标题最多输入 200 个字符。')
        term = query.strip()
        sql = '''FROM conversations c JOIN knowledge_bases k ON k.id=c.knowledge_base_id
            WHERE c.deleted_at IS NULL AND k.deleted_at IS NULL
            AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id=c.id)'''
        arguments: tuple = ()
        if term:
            sql += ' AND instr(lower(c.title), lower(?)) > 0'
            arguments = (term,)
        with self.connection() as connection:
            total = connection.execute('SELECT COUNT(*) ' + sql, arguments).fetchone()[0]
            rows = connection.execute('''SELECT c.*, k.name AS knowledge_base_name,
                (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count ''' + sql +
                ' ORDER BY c.updated_at DESC,c.id DESC LIMIT ? OFFSET ?', (*arguments, limit, offset)).fetchall()
        return {'items': [dict(row) for row in rows], 'total': total, 'has_more': offset + len(rows) < total}

    def rename_conversation(self, identifier: str, title: str) -> dict:
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 100:
            raise MiniimaError('对话标题应为 1–100 个字符。')
        with self.connection() as connection, connection:
            self._conversation(connection, identifier)
            connection.execute('UPDATE conversations SET title=?, updated_at=? WHERE id=?',
                               (title.strip(), now(), identifier))
        return self.get_conversation(identifier)

    def get_conversation(self, identifier: str) -> dict:
        with self.connection() as connection:
            result = self._conversation(connection, identifier)
            messages = [dict(row) for row in connection.execute(
                'SELECT * FROM messages WHERE conversation_id=? ORDER BY position', (identifier,))]
            citations = connection.execute('''SELECT mc.* FROM message_citations mc
                JOIN messages m ON m.id=mc.message_id WHERE m.conversation_id=?
                ORDER BY mc.citation_number''', (identifier,)).fetchall()
        by_message: dict[str, list] = {}
        for row in citations:
            by_message.setdefault(row['message_id'], []).append({**dict(row),
                'source_metadata': json.loads(row['source_metadata'])})
        result['messages'] = [{**message, 'citations': by_message.get(message['id'], [])} for message in messages]
        result['message_count'] = len(messages)
        return result

    def begin_turn(self, kb_reference: str, question: str, request_id: str,
                   conversation_id: str | None = None, *, retry: bool = False, web_search: bool = False) -> tuple[str, dict, bool]:
        question = question.strip()
        if not question or not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise MiniimaError('问题或请求编号无效。')
        kb = self.get_kb(kb_reference)
        timestamp = now()
        with self.connection() as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            self._active_kb(connection, kb['id'])
            old = connection.execute('SELECT * FROM messages WHERE request_id=?', (request_id,)).fetchone()
            if old:
                conversation = self._conversation(connection, old['conversation_id'])
                if (conversation['knowledge_base_id'] != kb['id'] or old['content'] != question
                        or (conversation_id and old['conversation_id'] != conversation_id)
                        or bool(old['web_search']) != web_search):
                    raise MiniimaError('请求编号已用于另一个问题。')
                conversation_id = old['conversation_id']
                if old['status'] == 'pending':
                    raise MiniimaError('这个问题仍在处理中，请稍后查看。')
                if old['status'] == 'completed' or not retry:
                    return conversation_id, dict(old), False
                if connection.execute("SELECT 1 FROM messages WHERE conversation_id=? AND status='pending'", (conversation_id,)).fetchone():
                    raise MiniimaError('该对话还有问题正在处理。')
                connection.execute("UPDATE messages SET status='pending',error=NULL,worker_pid=?,updated_at=? WHERE id=?",
                                   (os.getpid(), timestamp, old['id']))
                message = {**dict(old), 'status': 'pending', 'error': None}
            else:
                if retry:
                    raise MiniimaError('找不到需要重试的问题。')
                if conversation_id:
                    conversation = self._conversation(connection, conversation_id)
                    if conversation['knowledge_base_id'] != kb['id']:
                        raise MiniimaError('此对话绑定了另一个知识库，请新建对话。')
                else:
                    conversation_id = str(uuid.uuid4())
                    connection.execute('''INSERT INTO conversations
                        (id,knowledge_base_id,created_at,updated_at,title) VALUES (?,?,?,?,?)''',
                        (conversation_id, kb['id'], timestamp, timestamp, question[:30]))
                if connection.execute("SELECT 1 FROM messages WHERE conversation_id=? AND status='pending'", (conversation_id,)).fetchone():
                    raise MiniimaError('该对话还有问题正在处理。')
                last = connection.execute('SELECT position,role FROM messages WHERE conversation_id=? ORDER BY position DESC LIMIT 1', (conversation_id,)).fetchone()
                position = last['position'] + (2 if last['role'] == 'user' else 1) if last else 0
                message = {'id': str(uuid.uuid4()), 'conversation_id': conversation_id, 'role': 'user',
                           'content': question, 'request_id': request_id, 'status': 'pending', 'position': position,
                           'web_search': int(web_search)}
                connection.execute('''INSERT INTO messages
                    (id,conversation_id,role,content,created_at,updated_at,position,status,request_id,worker_pid,web_search)
                    VALUES (:id,:conversation_id,:role,:content,:time,:time,:position,:status,:request_id,:pid,:web_search)''',
                    {**message, 'time': timestamp, 'pid': os.getpid()})
            connection.execute('UPDATE conversations SET updated_at=? WHERE id=?', (timestamp, conversation_id))
        return conversation_id, message, True

    def retry_details(self, request_id: str) -> tuple[dict, dict]:
        with self.connection() as connection:
            message = connection.execute('SELECT * FROM messages WHERE request_id=?', (request_id,)).fetchone()
            if not message:
                raise MiniimaError('找不到需要重试的问题。')
            conversation = self._conversation(connection, message['conversation_id'])
        return conversation, dict(message)

    def complete_turn(self, user_id: str, text: str, citations: list[dict]) -> dict:
        timestamp, answer_id = now(), str(uuid.uuid4())
        with self.connection() as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            user = connection.execute('SELECT * FROM messages WHERE id=?', (user_id,)).fetchone()
            if not user or user['status'] != 'pending':
                raise MiniimaError('此问题已中断，请重新查看对话。')
            self._conversation(connection, user['conversation_id'])
            connection.execute('''INSERT INTO messages
                (id,conversation_id,role,content,created_at,updated_at,position,reply_to)
                VALUES (?,?,?,?,?,?,?,?)''',
                (answer_id, user['conversation_id'], 'assistant', text, timestamp, timestamp, user['position'] + 1, user_id))
            for citation in citations:
                connection.execute('''INSERT INTO message_citations
                    (id,message_id,chunk_id,citation_number,document_id,filename,content,source_metadata,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)''', (str(uuid.uuid4()), answer_id, citation.get('chunk_id', citation['id']), citation['citation_number'],
                    citation['document_id'], citation['filename'], citation['content'],
                    json.dumps(citation['source_metadata'], ensure_ascii=False), timestamp))
            connection.execute("UPDATE messages SET status='completed',error=NULL,worker_pid=NULL,updated_at=? WHERE id=?", (timestamp, user_id))
            connection.execute('UPDATE conversations SET updated_at=? WHERE id=?', (timestamp, user['conversation_id']))
        return self.get_conversation(user['conversation_id'])

    def fail_turn(self, user_id: str, error: str) -> None:
        with self.connection() as connection, connection:
            connection.execute("UPDATE messages SET status='failed',error=?,worker_pid=NULL,updated_at=? WHERE id=? AND status='pending'", (error, now(), user_id))

    def recover_interrupted(self) -> None:
        from miniima.storage.processes import process_alive
        with self.connection() as connection, connection:
            pids = connection.execute("SELECT DISTINCT worker_pid FROM messages WHERE status='pending'").fetchall()
            for row in pids:
                if not process_alive(row['worker_pid']):
                    connection.execute("""UPDATE messages SET status='interrupted',worker_pid=NULL,
                        error='上次处理已中断，可重试这个问题。',updated_at=? WHERE status='pending' AND worker_pid IS ?""", (now(), row['worker_pid']))

    def delete_conversation(self, identifier: str) -> None:
        with self.connection() as connection, connection:
            self._conversation(connection, identifier)
            connection.execute('UPDATE conversations SET deleted_at=? WHERE id=?', (now(), identifier))

    def list_trash(self) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute('''SELECT 'kb' AS kind,id,name AS title,name AS knowledge_base_name,
                id AS knowledge_base_id,deleted_at FROM knowledge_bases WHERE deleted_at IS NOT NULL
                UNION ALL SELECT 'conversation',c.id,c.title,k.name,c.knowledge_base_id,c.deleted_at
                FROM conversations c JOIN knowledge_bases k ON k.id=c.knowledge_base_id
                WHERE c.deleted_at IS NOT NULL ORDER BY deleted_at DESC,id''').fetchall()
        return [dict(row) for row in rows]

    def restore(self, kind: str, identifier: str) -> None:
        table = self._trash_table(kind)
        with self.connection() as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute(f'SELECT * FROM {table} WHERE id=? AND deleted_at IS NOT NULL', (identifier,)).fetchone()
            if not row:
                raise MiniimaError('回收站中找不到此项目。')
            if kind == 'conversation':
                parent = connection.execute('SELECT deleted_at FROM knowledge_bases WHERE id=?', (row['knowledge_base_id'],)).fetchone()
                if parent['deleted_at']:
                    raise MiniimaError('请先恢复所属知识库，再恢复此对话。')
            connection.execute(f'UPDATE {table} SET deleted_at=NULL WHERE id=?', (identifier,))

    @staticmethod
    def _trash_table(kind: str) -> str:
        if kind not in ('kb', 'conversation'):
            raise MiniimaError('回收站类型应为 kb 或 conversation。')
        return 'knowledge_bases' if kind == 'kb' else 'conversations'

    def purge(self, kind: str, identifier: str, cleanup=None) -> None:
        table = self._trash_table(kind)
        with self.connection() as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute(f'SELECT * FROM {table} WHERE id=? AND deleted_at IS NOT NULL', (identifier,)).fetchone()
            if not row:
                raise MiniimaError('回收站中找不到此项目。')
            if cleanup:
                cleanup(dict(row))
            connection.execute(f'DELETE FROM {table} WHERE id=?', (identifier,))

    def diagnostics(self) -> dict:
        with self.connection() as connection:
            return {"integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
                    "foreign_key_errors": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
                    "schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
                    "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0]}
