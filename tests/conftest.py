import json
from dataclasses import replace

import numpy as np
import pytest

from miniima.config import Settings, save_settings
from miniima.errors import ProviderError
from miniima.storage.repository import Repository


class MockProvider:
    """Deterministic test vectors, never advertised as real semantic embeddings."""
    def __init__(self):
        self.embedding_calls = 0
        self.chat_calls = 0
        self.fail = False
        self.last_messages = None

    def embed(self, texts):
        self.embedding_calls += 1
        if self.fail:
            raise ProviderError("模拟 API 超时。")
        vectors = []
        for text in texts:
            vector = np.zeros(8, dtype=np.float32)
            vector[0 if "TCP" in text else 1 if "以太网" in text else 2] = 1
            vectors.append(vector)
        return np.asarray(vectors, dtype=np.float32)

    def chat(self, messages):
        self.chat_calls += 1
        self.last_messages = messages
        evidence = json.loads(messages[-1]["content"])["untrusted_reference_data"]
        return f"根据资料，{evidence[0]['content']} [1]"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    import os
    for name in tuple(os.environ):
        if name.startswith("MINIIMA_"):
            monkeypatch.delenv(name)


@pytest.fixture
def settings():
    return replace(Settings(), api_key="mock-chat-key", embedding_api_key="mock-embedding-key",
                   embedding_base_url="https://embedding.test/v1", embedding_model="mock-embedding",
                   embedding_dimension=8, retrieval_engine="numpy")


@pytest.fixture
def repository(tmp_path, settings):
    repository = Repository(tmp_path / "home")
    repository.initialize()
    save_settings(settings, repository.home)
    return repository


@pytest.fixture
def provider():
    return MockProvider()
