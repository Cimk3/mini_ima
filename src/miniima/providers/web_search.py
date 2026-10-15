"""Credential-free, bounded retrieval from public Bing RSS / DuckDuckGo HTML."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from miniima.errors import ProviderError


def public_url(value: str) -> str | None:
    try:
        if len(value) > 4096 or any(ord(char) < 32 for char in value):
            return None
        url = urlsplit(value)
        return value if url.scheme in ('http', 'https') and url.hostname and not (url.username or url.password) else None
    except ValueError:
        return None


class SearchResults(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self.current: dict | None = None
        self.capture: str | None = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get('class', '').split()
        if tag == 'a' and 'result__a' in classes:
            href = urljoin('https://duckduckgo.com', attributes.get('href', ''))
            if urlsplit(href).hostname in ('duckduckgo.com', 'www.duckduckgo.com'):
                href = parse_qs(urlsplit(href).query).get('uddg', [''])[0]
            self.current = {'url': public_url(href), 'title': '', 'snippet': ''}
            self.results.append(self.current)
            self.capture, self.depth = 'title', 1
        elif self.current is not None and 'result__snippet' in classes:
            self.capture, self.depth = 'snippet', 1
        elif self.capture and tag not in ('br', 'img', 'hr', 'input', 'meta', 'link', 'wbr'):
            self.depth += 1

    def handle_endtag(self, tag):
        if self.capture and tag not in ('br', 'img', 'hr', 'input', 'meta', 'link', 'wbr'):
            self.depth -= 1
            if self.depth <= 0:
                self.capture = None

    def handle_data(self, data):
        if self.capture and self.current is not None:
            self.current[self.capture] += data


def search_web(question: str, limit: int = 5) -> list[dict]:
    # A fresh standard-library request cannot inherit the model client's API keys.
    # Only the current question is sent, never local documents or chat history.
    query = question.strip()[:1000]
    providers = [
        ('Bing', 'https://www.bing.com/search?' + urlencode({'format': 'rss', 'q': query})),
        ('DuckDuckGo', 'https://html.duckduckgo.com/html/?' + urlencode({'q': query})),
    ]
    for engine, url in providers:
        request = Request(url, headers={'User-Agent': 'Mozilla/5.0 Miniima/0.1', 'Accept': 'application/rss+xml, text/html'})
        try:
            with urlopen(request, timeout=8) as response:
                payload = response.read(1_000_001)
                if len(payload) > 1_000_000:
                    raise ValueError('response too large')
            if engine == 'Bing':
                root = ElementTree.fromstring(payload)
                results = [{'url': item.findtext('link', ''), 'title': item.findtext('title', ''),
                            'snippet': item.findtext('description', '')} for item in root.findall('./channel/item')]
            else:
                parser = SearchResults()
                parser.feed(payload.decode('utf-8', errors='replace'))
                results = parser.results
            matches = _snapshots(results, engine, limit)
            if matches:
                return matches
        except Exception:
            continue
    raise ProviderError('联网搜索暂不可用：网络超时、搜索验证或没有可用结果。请稍后重试，或关闭联网搜索后重新提问。')


def _snapshots(results: list[dict], engine: str, limit: int) -> list[dict]:
    matches, seen = [], set()
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for item in results:
        address = public_url(item['url']) if item['url'] else None
        title = ' '.join(item['title'].split())[:250]
        snippet = ' '.join(item['snippet'].split())[:1200]
        if not address or not title or not snippet or address in seen:
            continue
        seen.add(address)
        identifier = 'web:' + hashlib.sha256(address.encode()).hexdigest()
        matches.append({'id': identifier, 'chunk_id': None, 'document_id': identifier,
                        'filename': title, 'content': snippet,
                        'source_metadata': {'kind': 'web', 'url': address, 'retrieved_at': retrieved_at, 'search_engine': engine,
                                            'line_start': 0, 'line_end': 0, 'heading_path': [title]}})
        if len(matches) >= limit:
            break
    return matches
