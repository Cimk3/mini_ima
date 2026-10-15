from pathlib import Path

from miniima.errors import MiniimaError


def parse(path: Path):
    if path.suffix.lower() not in (".txt", ".md", ".markdown"):
        raise MiniimaError("阶段一、二仅支持 TXT/Markdown；其他格式属于阶段三。")
    from miniima.documents.parsers.text import parse_text

    return parse_text(path)
