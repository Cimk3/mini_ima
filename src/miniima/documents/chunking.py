from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from itertools import groupby

from miniima.documents.parsers.text import TextBlock

# Lightweight estimate: one CJK character or four ASCII word characters per token.
# This is deliberately not presented as the model's exact tokenizer.
TOKEN = re.compile(r"[A-Za-z0-9_]{1,4}|[^\s]", re.UNICODE)


def estimate_tokens(text: str) -> int:
    return sum(1 for _ in TOKEN.finditer(text))


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    content: str
    chunk_index: int
    source_type: str
    source_metadata: dict


def make_chunks(blocks: list[TextBlock], document_id: str, source_type: str,
                target: int = 500, overlap: int = 80) -> list[Chunk]:
    if target < 1 or not 0 <= overlap < target:
        raise ValueError("invalid chunk size or overlap")
    chunks: list[Chunk] = []
    for heading_path, section in groupby(blocks, key=lambda block: tuple(block.metadata["heading_path"])):
        section = list(section)
        pieces: list[str] = []
        spans: list[tuple[int, int, TextBlock]] = []
        position = 0
        for block in section:
            if pieces:
                pieces.append("\n\n")
                position += 2
            pieces.append(block.content)
            spans.append((position, position + len(block.content), block))
            position += len(block.content)
        text = "".join(pieces)
        tokens = list(TOKEN.finditer(text))
        start = 0
        while start < len(tokens):
            end = min(start + target, len(tokens))
            if end < len(tokens):
                lower = start + max(overlap + 1, target // 2)
                for candidate in range(end, lower - 1, -1):
                    gap = text[tokens[candidate - 1].end():tokens[candidate].start()]
                    if "\n\n" in gap:
                        end = candidate
                        break
                else:
                    for candidate in range(end, lower - 1, -1):
                        if tokens[candidate - 1].group() in ("。", "！", "？", ".", "!", "?", ";", "；"):
                            end = candidate
                            break
            begin_char, end_char = tokens[start].start(), tokens[end - 1].end()
            sources = [block for begin, finish, block in spans if begin < end_char and finish > begin_char]
            chunks.append(Chunk(str(uuid.uuid4()), document_id, text[begin_char:end_char].strip(),
                                len(chunks), source_type, {
                                    "line_start": min(item.metadata["line_start"] for item in sources),
                                    "line_end": max(item.metadata["line_end"] for item in sources),
                                    "heading_path": list(heading_path),
                                }))
            if end == len(tokens):
                break
            start = max(start + 1, end - overlap)
    return chunks
