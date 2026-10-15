from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from miniima.config import Settings
from miniima.documents.chunking import make_chunks
from miniima.documents.parsers import parse
from miniima.errors import MiniimaError
from miniima.providers.openai_compatible import OpenAICompatibleProvider
from miniima.rag.answering import build_prompt, validate_citations
from miniima.storage.repository import Repository
from miniima.vector import create_index
from miniima.vector.numpy_index import validate_vectors


@dataclass(frozen=True)
class Answer:
    text: str
    citations: list[dict]
    conversation_id: str


class KnowledgeService:
    def __init__(self, repository: Repository, settings: Settings, provider=None):
        self.repository = repository
        self.settings = settings
        self.provider = provider or OpenAICompatibleProvider(settings)

    def _compatible(self, kb: dict) -> None:
        if (kb["embedding_model"], kb["embedding_dimension"], kb["embedding_base_url"]) != (
                self.settings.embedding_model, self.settings.embedding_dimension, self.settings.embedding_url):
            raise MiniimaError("当前向量配置与知识库绑定的模型、维度或服务地址不一致。"
                               "请恢复原配置，或创建新知识库后重新导入。")

    def delete_kb(self, reference: str) -> dict:
        """Both interfaces move a knowledge base to the recoverable trash."""
        return self.repository.delete_kb(reference)

    def add(self, path: Path, reference: str) -> tuple[dict, bool]:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise MiniimaError("找不到可读取的文档文件。")
        suffix = path.suffix.lower()
        if suffix not in (".txt", ".md", ".markdown"):
            raise MiniimaError("阶段一、二仅支持 TXT/Markdown；其他格式属于阶段三。")
        kb = self.repository.get_kb(reference)
        self._compatible(kb)
        directory = self.repository.home / "originals" / kb["id"]
        directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".staging-", suffix=suffix, dir=directory)
        staging = Path(temporary)
        final_path = None
        document = None
        moved = False
        try:
            digest = hashlib.sha256()
            # Parse exactly the bytes that were hashed, even if the input changes during import.
            with os.fdopen(fd, "wb") as destination, path.open("rb") as source:
                while block := source.read(1024 * 1024):
                    digest.update(block)
                    destination.write(block)
            old = self.repository.find_document(kb["id"], digest.hexdigest())
            if old and old["status"] == "ready":
                return old, False
            identifier = old["id"] if old else str(uuid.uuid4())
            final_path = directory / f"{identifier}{suffix}"
            document = {"id": identifier, "knowledge_base_id": kb["id"], "filename": path.name,
                        "sha256": digest.hexdigest(), "source_type": "txt" if suffix == ".txt" else "markdown",
                        "original_path": str(final_path.relative_to(self.repository.home))}
            blocks = parse(staging)
            chunks = make_chunks(blocks, identifier, document["source_type"],
                                 self.settings.chunk_tokens, self.settings.chunk_overlap)
            vectors = self.provider.embed([chunk.content for chunk in chunks])
            validate_vectors(vectors, kb["embedding_dimension"])
            if len(vectors) != len(chunks):
                raise MiniimaError("Embedding 返回数量与 Chunk 数量不符。")
            os.replace(staging, final_path)
            moved = True
            imported = self.repository.store_document(document, chunks, vectors, kb)
            stored = self.repository.find_document(kb["id"], document["sha256"])
            if not imported and stored["id"] != identifier:
                final_path.unlink(missing_ok=True)
            return stored, imported
        except Exception as exc:
            if document:
                # A competing import may already have committed this hash. Preserve its data.
                existing = self.repository.find_document(kb["id"], document["sha256"])
                if not existing or existing["status"] != "ready":
                    message = str(exc) if isinstance(exc, MiniimaError) else "解析、向量校验或存储失败。"
                    self.repository.record_failure(document, message)
                    if moved and final_path:
                        final_path.unlink(missing_ok=True)
            raise
        finally:
            staging.unlink(missing_ok=True)

    def search(self, question: str, reference: str, top_k: int = 5, *, engine: str | None = None) -> list[dict]:
        if not question.strip():
            raise MiniimaError("查询内容不能为空。")
        if not 1 <= top_k <= 100:
            raise MiniimaError("top-k 应在 1–100 之间。")
        kb = self.repository.get_kb(reference)
        self._compatible(kb)
        ids, vectors = self.repository.index_data(kb)
        if not ids:
            return []
        index = create_index(kb["embedding_dimension"], engine or self.settings.retrieval_engine)
        try:
            index.rebuild(ids, vectors)
            query = self.provider.embed([question])
            if query.shape != (1, kb["embedding_dimension"]):
                raise ValueError("query dimension mismatch")
            ranked = index.search(query[0], top_k)
        except (ValueError, TypeError) as exc:
            raise MiniimaError("检索向量无效或与知识库维度不一致。") from exc
        chunks = self.repository.get_chunks(kb["id"], [item[0] for item in ranked])
        return [{**chunks[identifier], "score": score} for identifier, score in ranked if identifier in chunks]

    def ask(self, question: str, reference: str, top_k: int = 5, *, engine: str | None = None) -> Answer:
        kb = self.repository.get_kb(reference)
        matches = [match for match in self.search(question, reference, top_k, engine=engine)
                   if match["score"] >= self.settings.min_score]
        messages, sources = build_prompt(question, matches, self.settings.context_tokens)
        if not sources:
            text, citations = "知识库证据不足：没有找到达到检索阈值的可用资料。", []
        else:
            text, citations = validate_citations(self.provider.chat(messages), sources)
        conversation_id = self.repository.save_answer(kb["id"], question, text, citations)
        return Answer(text, citations, conversation_id)
