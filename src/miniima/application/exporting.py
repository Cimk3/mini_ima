"""Offline Markdown export using saved conversation and citation snapshots only."""
from __future__ import annotations

import re
from datetime import datetime
from html import escape

from miniima.errors import MiniimaError
from miniima.providers.web_search import public_url


def plain(value) -> str:
    return re.sub(r'([\\`*_\[\]#])', r'\\\1', escape(str(value)).replace('\r', ' ').replace('\n', ' '))


def excerpt(text: str) -> str:
    fence = '`' * max(3, max((len(item) + 1 for item in re.findall(r'`+', text)), default=0))
    return f'{fence}text\n{text}\n{fence}'


def export_conversation(conversation: dict, *, at: datetime | None = None) -> dict:
    messages = conversation['messages']
    if not messages:
        raise MiniimaError('空白对话没有可导出的内容。')
    if any(message['status'] == 'pending' for message in messages):
        raise MiniimaError('当前对话仍在生成，请停止或完成后再导出。')
    at = at or datetime.now().astimezone()
    title = conversation['title']
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)[:60].rstrip(' .') or '对话'
    lines = [f'# {plain(title)}', '', f'知识库：{plain(conversation["knowledge_base_name"])}', '',
             f'创建时间：{plain(conversation["created_at"])}', '', f'导出时间：{at.isoformat(timespec="seconds")}', '']
    states = {'completed': '已完成', 'failed': '生成失败，未完成', 'interrupted': '已中断，未完成'}
    turn = 0
    for message in messages:
        if message['role'] == 'user':
            turn += 1
            lines.extend([f'## 第 {turn} 轮', '', '### 问题', '', message['content'], '',
                          f'状态：{states.get(message["status"], "未完成")}', ''])
            if message.get('error'):
                lines.extend([f'说明：{plain(message["error"])}', ''])
        else:
            lines.extend(['### 回答', '', message['content'], ''])
            if message['status'] != 'completed':
                lines.extend([f'> {states.get(message["status"], "未完成")}；来源尚未校验。', ''])
                continue
            if not message['citations']:
                continue
            lines.extend([f'### 第 {turn} 轮来源', '', '以下编号仅对应本轮回答。', ''])
            for source in message['citations']:
                metadata = source['source_metadata']
                lines.extend([f'#### [{source["citation_number"]}] {plain(source["filename"])}', ''])
                if metadata.get('kind') == 'web':
                    url = public_url(metadata.get('url', ''))
                    if url:
                        lines.extend([f'网页：<{url.replace(">", "%3E").replace("<", "%3C")}>', ''])
                    lines.extend([f'检索时间：{plain(metadata.get("retrieved_at", "未记录"))}', ''])
                else:
                    lines.extend([f'位置：行 {metadata.get("line_start", "?")}–{metadata.get("line_end", "?")}', '',
                                  f'标题路径：{plain(" / ".join(metadata.get("heading_path", [])) or "文档片段")}', ''])
                lines.extend([excerpt(source['content']), ''])
    return {'filename': f'Miniima-{safe_title}-{at:%Y%m%d}.md', 'markdown': '\n'.join(lines).rstrip() + '\n'}
