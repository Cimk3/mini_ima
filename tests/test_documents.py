from miniima.documents.chunking import estimate_tokens, make_chunks
from miniima.documents.parsers import parse
from miniima.errors import MiniimaError

import pytest


def test_markdown_structure_and_code_fence(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# 网络\n\nTCP 三次握手。\n\n## 代码\n```python\n# not a heading\n```\n", encoding="utf-8")
    blocks = parse(path)
    assert blocks[1].metadata == {"line_start": 3, "line_end": 3, "heading_path": ["网络"]}
    assert blocks[-1].metadata["heading_path"] == ["网络", "代码"]
    assert "# not a heading" in blocks[-1].content
    chunks = make_chunks(blocks, "doc", "markdown")
    assert len(chunks) == 2
    assert chunks[1].source_metadata["heading_path"] == ["网络", "代码"]


def test_chunk_limits_overlap_and_complete_coverage(tmp_path):
    path = tmp_path / "long.txt"
    text = "".join(chr(0x4E00 + i) for i in range(201))
    path.write_text(text, encoding="utf-8")
    chunks = make_chunks(parse(path), "doc", "txt", target=50, overlap=10)
    assert all(estimate_tokens(chunk.content) <= 50 for chunk in chunks)
    assert chunks[0].content[-10:] == chunks[1].content[:10]
    assert set("".join(chunk.content for chunk in chunks)) == set(text)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_bom_and_unicode(tmp_path, encoding):
    path = tmp_path / "中文.txt"
    path.write_text("你好\n\n世界", encoding=encoding)
    assert [item.content for item in parse(path)] == ["你好", "世界"]


@pytest.mark.parametrize("data", [b"  \n\t", b"binary\x00data", b"\xffbad"])
def test_empty_binary_and_bad_encoding_are_rejected(tmp_path, data):
    path = tmp_path / "invalid.txt"
    path.write_bytes(data)
    with pytest.raises(MiniimaError):
        parse(path)
