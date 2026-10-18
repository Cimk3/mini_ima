import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from miniima.errors import ProviderError
from miniima.providers.openai_compatible import OpenAICompatibleProvider


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks, self.closed = chunks, False

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk

    async def aclose(self):
        self.closed = True


def sse(delta=None, finish=None, *, empty=False):
    choices = [] if empty else [{'index': 0, 'delta': delta or {}, 'finish_reason': finish}]
    return ('data: ' + json.dumps({'id': 'fake-stream', 'object': 'chat.completion.chunk',
        'created': 1, 'model': 'test', 'choices': choices}) + '\n\n').encode()


def provider_with_stream(settings, chunks):
    body = Stream(chunks)
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=body)
    def factory(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    return OpenAICompatibleProvider(settings, async_client_factory=factory), body, requests


def test_sdk_stream_handles_role_empty_choices_and_closes_response(settings):
    provider, body, requests = provider_with_stream(settings, [sse({'role': 'assistant', 'content': ''}),
        sse({'content': '中文'}), sse(empty=True), sse({'content': '回答[1]'}), sse(finish='stop'), b'data: [DONE]\n\n'])
    async def collect():
        return [part async for part in provider.stream_chat([{'role': 'user', 'content': 'test'}])]
    assert asyncio.run(collect()) == ['中文', '回答[1]']
    assert body.closed and len(requests) == 1 and requests[0]['stream'] is True


@pytest.mark.parametrize('finish,expected', [('length', '长度限制'), (None, '意外中断')])
def test_truncation_and_missing_finish_are_failures_without_replaying(settings, finish, expected):
    chunks = [sse({'content': '已收到的部分'})]
    if finish:
        chunks.append(sse(finish=finish))
    chunks.append(b'data: [DONE]\n\n')
    provider, body, requests = provider_with_stream(settings, chunks)
    received = []
    async def collect():
        async for part in provider.stream_chat([{'role': 'user', 'content': 'test'}]):
            received.append(part)
    with pytest.raises(ProviderError, match=expected):
        asyncio.run(collect())
    assert received == ['已收到的部分'] and body.closed and len(requests) == 1


def test_cancel_releases_actual_sdk_response(settings):
    provider, body, _ = provider_with_stream(settings, [sse({'content': '片段'}), sse(finish='stop')])
    async def collect():
        async for _ in provider.stream_chat([{'role': 'user', 'content': 'test'}]):
            asyncio.current_task().cancel()
            await asyncio.sleep(0)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(collect())
    assert body.closed


def test_http_error_is_sanitized_and_not_automatically_retried(settings):
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={'error': {'message': 'secret-provider-body'}})
    def factory(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    provider = OpenAICompatibleProvider(settings, async_client_factory=factory)
    async def collect():
        return [part async for part in provider.stream_chat([{'role': 'user', 'content': 'test'}])]
    with pytest.raises(ProviderError) as error:
        asyncio.run(collect())
    assert 'secret-provider-body' not in str(error.value) and len(calls) == 1
