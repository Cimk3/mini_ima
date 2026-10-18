from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import urlsplit

import numpy as np
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, AsyncOpenAI, OpenAI

from miniima.config import QWEN_EMBEDDING_BATCH_LIMIT, QWEN_EMBEDDING_MODEL, Settings
from miniima.errors import ProviderError
from miniima.vector.numpy_index import validate_vectors


@contextmanager
def api_errors():
    try:
        yield
    except APITimeoutError as exc:
        raise ProviderError("API 请求超时，请检查网络或增加 --timeout。") from exc
    except APIConnectionError as exc:
        raise ProviderError("无法连接 API，请检查地址、代理和网络。") from exc
    except APIStatusError as exc:
        descriptions = {401: "API Key 无效", 402: "账户余额不足", 403: "访问被拒绝",
                        404: "接口或模型不存在", 429: "请求频率或配额超限"}
        # Do not expose provider error bodies: they can echo credentials and documents.
        description = descriptions.get(exc.status_code, "服务端请求失败")
        raise ProviderError(f"API 错误 HTTP {exc.status_code}：{description}。") from exc
    except APIError as exc:
        raise ProviderError("API 返回异常，请检查模型及服务配置。") from exc


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings, client_factory=OpenAI, async_client_factory=AsyncOpenAI):
        self.settings = settings
        self._client_factory = client_factory
        self._async_client_factory = async_client_factory

    def _client(self, *, embedding: bool):
        return self._client_factory(
            api_key=self.settings.embedding_key if embedding else self.settings.api_key,
            base_url=self.settings.embedding_url if embedding else self.settings.base_url,
            timeout=self.settings.timeout,
            max_retries=self.settings.max_retries,
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        self.settings.require_embedding()
        dimension = self.settings.embedding_dimension
        if not texts:
            return np.empty((0, dimension), dtype=np.float32)
        vectors = []
        batch_size = self.settings.embedding_batch_size
        options = {}
        if self.settings.embedding_model == QWEN_EMBEDDING_MODEL:
            batch_size = min(batch_size, QWEN_EMBEDDING_BATCH_LIMIT)
            options["dimensions"] = dimension
        with api_errors(), self._client(embedding=True) as client:
            for start in range(0, len(texts), batch_size):
                batch = texts[start:start + batch_size]
                response = client.embeddings.create(model=self.settings.embedding_model,
                                                    input=batch, encoding_format="float", **options)
                items = sorted(response.data, key=lambda item: item.index)
                if [item.index for item in items] != list(range(len(batch))):
                    raise ProviderError("Embedding 返回的数量或索引异常。")
                vectors.extend(item.embedding for item in items)
        try:
            result = np.asarray(vectors, dtype=np.float32)
            validate_vectors(result, dimension)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ProviderError("Embedding 维度不符，或包含零向量、NaN/Inf。请检查模型和维度。") from exc
        return np.ascontiguousarray(result, dtype=np.float32)

    def _chat_options(self) -> dict:
        options = {}
        if urlsplit(self.settings.base_url).hostname == "api.deepseek.com" and self.settings.chat_model in (
                "deepseek-flash", "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"):
            # These models default to thinking, which can exhaust the answer's token budget.
            options["extra_body"] = {"thinking": {"type": "disabled"}}
        return options

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.settings.require_chat()
        options = self._chat_options()
        with api_errors(), self._client(embedding=False) as client:
            response = client.chat.completions.create(
                model=self.settings.chat_model, messages=messages, temperature=0, max_tokens=2048,
                **options,
            )
        if not response.choices or not response.choices[0].message.content:
            raise ProviderError("Chat API 未返回可用的回答。")
        if response.choices[0].finish_reason == "length":
            raise ProviderError("模型回答因输出长度限制被截断，请缩小问题后重试。")
        return response.choices[0].message.content

    def _async_client(self, *, embedding: bool = False):
        # A failed generation is explicitly retried by the user, never replayed by the SDK.
        return self._async_client_factory(
            api_key=self.settings.embedding_key if embedding else self.settings.api_key,
            base_url=self.settings.embedding_url if embedding else self.settings.base_url,
            timeout=self.settings.timeout, max_retries=0)

    async def aembed(self, texts: list[str]) -> np.ndarray:
        self.settings.require_embedding()
        dimension = self.settings.embedding_dimension
        if not texts:
            return np.empty((0, dimension), dtype=np.float32)
        options, batch_size = {}, self.settings.embedding_batch_size
        if self.settings.embedding_model == QWEN_EMBEDDING_MODEL:
            options['dimensions'] = dimension
            batch_size = min(batch_size, QWEN_EMBEDDING_BATCH_LIMIT)
        vectors = []
        with api_errors():
            async with self._async_client(embedding=True) as client:
                for start in range(0, len(texts), batch_size):
                    batch = texts[start:start + batch_size]
                    response = await client.embeddings.create(model=self.settings.embedding_model,
                        input=batch, encoding_format='float', **options)
                    items = sorted(response.data, key=lambda item: item.index)
                    if [item.index for item in items] != list(range(len(batch))):
                        raise ProviderError('Embedding 返回的数量或索引异常。')
                    vectors.extend(item.embedding for item in items)
        try:
            result = np.asarray(vectors, dtype=np.float32)
            validate_vectors(result, dimension)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ProviderError('Embedding 维度不符，或包含零向量、NaN/Inf。请检查模型和维度。') from exc
        return np.ascontiguousarray(result, dtype=np.float32)

    async def achat(self, messages: list[dict[str, str]]) -> str:
        self.settings.require_chat()
        with api_errors():
            async with self._async_client() as client:
                response = await client.chat.completions.create(model=self.settings.chat_model,
                    messages=messages, temperature=0, max_tokens=2048, **self._chat_options())
        if not response.choices or not response.choices[0].message.content:
            raise ProviderError('Chat API 未返回可用的回答。')
        if response.choices[0].finish_reason == 'length':
            raise ProviderError('模型回答因输出长度限制被截断，请缩小问题后重试。')
        return response.choices[0].message.content

    async def stream_chat(self, messages: list[dict[str, str]]):
        self.settings.require_chat()
        finish, received = None, False
        with api_errors():
            async with self._async_client() as client:
                stream = await client.chat.completions.create(model=self.settings.chat_model,
                    messages=messages, temperature=0, max_tokens=2048, stream=True, **self._chat_options())
                if not hasattr(stream, '__aiter__'):
                    raise ProviderError('服务未返回流式响应，请在设置中关闭流式显示后重试。')
                async with stream:
                    async for chunk in stream:
                        if not chunk.choices:
                            continue
                        choice = chunk.choices[0]
                        if choice.delta.content:
                            received = True
                            yield choice.delta.content
                        if choice.finish_reason:
                            finish = choice.finish_reason
        if finish == 'length':
            raise ProviderError('模型回答因输出长度限制被截断，请缩小问题后重试。')
        if not received:
            raise ProviderError('Chat API 未返回可用的流式回答，请在模型设置中关闭流式显示后重试。')
        if finish != 'stop':
            raise ProviderError('流式回答意外中断，已保留收到的内容；可重新生成或关闭流式显示后重试。')

    def test_chat(self) -> str:
        return self.chat([{"role": "user", "content": "请只回复 OK。"}])

    def test_embedding(self) -> int:
        return self.embed(["Mini-ima 连接测试"])[0].size
