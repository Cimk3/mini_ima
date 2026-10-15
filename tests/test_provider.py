import json
from dataclasses import replace

import httpx
import numpy as np
import pytest
from openai import OpenAI

from miniima.errors import ProviderError
from miniima.providers.openai_compatible import OpenAICompatibleProvider


def provider_with_transport(settings, handler):
    return OpenAICompatibleProvider(settings, client_factory=lambda **kwargs: OpenAI(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler))))


def test_sdk_routes_batching_order_keys_and_chat(settings):
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(request)
        if request.url.path.endswith("/embeddings"):
            assert request.headers["Authorization"] == "Bearer mock-embedding-key"
            assert body["model"] == "mock-embedding"
            assert "dimensions" not in body
            return httpx.Response(200, json={"object": "list", "model": body["model"], "data": [
                {"object": "embedding", "index": i, "embedding": [float(i + 1)] + [0.] * 7}
                for i in reversed(range(len(body["input"])))], "usage": {"prompt_tokens": 1, "total_tokens": 1}})
        assert request.url.host == "api.deepseek.com"
        assert request.headers["Authorization"] == "Bearer mock-chat-key"
        assert body["thinking"] == {"type": "disabled"}
        return httpx.Response(200, json={"id": "chat-test", "object": "chat.completion", "created": 0,
            "model": body["model"], "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"},
                                                "finish_reason": "stop"}]})
    provider = provider_with_transport(replace(settings, embedding_batch_size=2), handler)
    vectors = provider.embed(["a", "b", "c"])
    assert vectors.shape == (3, 8) and vectors.dtype == np.float32
    assert list(vectors[:, 0]) == [1., 2., 1.]
    assert provider.test_chat() == "OK"
    assert len(requests) == 3


@pytest.mark.parametrize("vector", [[0.] * 8, [1.] * 7, [float("nan")] + [1.] * 7,
                                    [float("inf")] + [1.] * 7])
def test_bad_vectors_rejected(settings, vector):
    def handler(request):
        return httpx.Response(200, content=json.dumps({"object": "list", "model": "mock-embedding",
            "data": [{"object": "embedding", "index": 0, "embedding": vector}]}).encode(),
            headers={"content-type": "application/json"})
    with pytest.raises(ProviderError):
        provider_with_transport(settings, handler).embed(["text"])


def test_retries_are_bounded_and_errors_do_not_echo_secrets(settings, monkeypatch):
    calls = []
    monkeypatch.setattr("openai._base_client.time.sleep", lambda seconds: None)
    def handler(request):
        calls.append(request)
        return httpx.Response(500, json={"error": {"message": "secret mock-chat-key user document"}})
    with pytest.raises(ProviderError) as error:
        provider_with_transport(settings, handler).test_chat()
    assert len(calls) == settings.max_retries + 1
    assert "mock-chat-key" not in str(error.value) and "document" not in str(error.value)


def test_auth_failure_is_not_retried(settings):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "bad key"}})
    with pytest.raises(ProviderError, match="401"):
        provider_with_transport(settings, handler).test_chat()
    assert len(calls) == 1


def test_other_chat_services_do_not_receive_deepseek_options(settings):
    def handler(request):
        assert "thinking" not in json.loads(request.content)
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0,
            "model": "other", "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"},
                                             "finish_reason": "stop"}]})
    provider = provider_with_transport(replace(settings, base_url="https://another.test/v1"), handler)
    assert provider.test_chat() == "OK"


@pytest.mark.parametrize("content,finish_reason", [(None, "stop"), ("partial [1]", "length")])
def test_empty_and_truncated_chat_answers_rejected(settings, content, finish_reason):
    def handler(request):
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0,
            "model": "other", "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                                             "finish_reason": finish_reason}]})
    with pytest.raises(ProviderError):
        provider_with_transport(settings, handler).test_chat()
