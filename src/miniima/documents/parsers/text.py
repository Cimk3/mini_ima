from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from miniima.errors import MiniimaError


@dataclass(frozen=True)
class TextBlock:
    content: str
    metadata: dict


def parse_text(path: Path) -> list[TextBlock]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    except UnicodeError as exc:
        raise MiniimaError("文本编码不受支持，请转为 UTF-8 或带 BOM 的 UTF-16。") from exc
    if "\x00" in text:
        raise MiniimaError("文件包含二进制内容，无法作为文本导入。")
    markdown = path.suffix.lower() != ".txt"
    headings: list[tuple[int, str]] = []
    blocks: list[TextBlock] = []
    buffer: list[str] = []
    start = 1
    fence: str | None = None

    def flush(end: int) -> None:
        if buffer and "\n".join(buffer).strip():
            blocks.append(TextBlock("\n".join(buffer).strip(), {
                "line_start": start,
                "line_end": end,
                "heading_path": [title for _, title in headings],
            }))
        buffer.clear()

    lines = text.splitlines()
    for number, line in enumerate(lines, 1):
        heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line) if markdown and not fence else None
        if heading:
            flush(number - 1)
            level, title = len(heading[1]), heading[2]
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, title))
            blocks.append(TextBlock(line.strip(), {
                "line_start": number, "line_end": number,
                "heading_path": [item[1] for item in headings], "heading_level": level,
            }))
            continue
        delimiter = re.match(r"^\s{0,3}(`{3,}|~{3,})", line) if markdown else None
        if delimiter:
            if fence is None:
                fence = delimiter[1][0]
            elif delimiter[1][0] == fence:
                fence = None
        if not line.strip() and not fence:
            flush(number - 1)
        else:
            if not buffer:
                start = number
            buffer.append(line)
    flush(len(lines))
    if not blocks:
        raise MiniimaError("文档不包含可提取文本，未导入任何内容。")
    return blocks
