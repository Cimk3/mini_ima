import json
from dataclasses import replace

import httpx
import numpy as np
import pytest
from openai import OpenAI
from typer.testing import CliRunner

from miniima.cli import app
from miniima.config import (QWEN_EMBEDDING_BASE_URL, QWEN_EMBEDDING_MODEL,
                           Settings, load_settings, qwen_settings, save_settings)
from miniima.errors import ConfigurationError
from miniima.providers.openai_compatible import OpenAICompatibleProvider


def sdk_provider(settings, handler):
    return OpenAICompatibleProvider(settings, client_factory=lambda **kwargs: OpenAI(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler))))


@pytest.mark.parametrize("url", [QWEN_EMBEDDING_BASE_URL, "https://maas.qianwenaiapi.com/compatible-mode/v1"])
def test_key_only_qwen_preset_preserves_chat_and_shows_input(tmp_path, settings, monkeypatch, url):
    monkeypatch.setenv("MINIIMA_HOME", str(tmp_path))
    save_settings(settings, tmp_path)
    arguments = ["config", "qwen"]
    if url != QWEN_EMBEDDING_BASE_URL:
        arguments += ["--base-url", url]
    result = CliRunner().invoke(app, arguments, input="qwen-test-key\n")
    assert result.exit_code == 0, result.output
    assert "qwen-test-key" in result.output
    configured = load_settings()
    assert configured.embedding_api_key == "qwen-test-key"
    assert configured.embedding_model == QWEN_EMBEDDING_MODEL
    assert configured.embedding_url == url
    assert configured.embedding_dimension == 1024
    assert configured.embedding_batch_size == 20
    assert (configured.api_key, configured.base_url, configured.chat_model) == (
        settings.api_key, settings.base_url, settings.chat_model)
    assert "qwen-test-key" not in CliRunner().invoke(app, ["config", "show"]).output


def test_legacy_blank_embedding_config_only_needs_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIIMA_HOME", str(tmp_path))
    save_settings(Settings(api_key="existing-chat-key"), tmp_path)
    result = CliRunner().invoke(app, ["config", "set", "--embedding-api-key"], input="qwen-test-key\n")
    assert result.exit_code == 0, result.output
    settings = load_settings()
    assert settings.embedding_model == QWEN_EMBEDDING_MODEL
    assert settings.embedding_dimension == 1024 and settings.embedding_url == QWEN_EMBEDDING_BASE_URL
    assert settings.api_key == "existing-chat-key"


def test_qwen_setup_can_test_connection_with_visible_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIIMA_HOME", str(tmp_path))
    calls = []
    def test_embedding(provider):
        calls.append(provider.settings)
        assert provider.settings.embedding_model == QWEN_EMBEDDING_MODEL
        assert provider.settings.embedding_key == "qwen-test-key"
        return 1024
    monkeypatch.setattr(OpenAICompatibleProvider, "test_embedding", test_embedding)
    result = CliRunner().invoke(app, ["config", "qwen", "--test"], input="qwen-test-key\n")
    assert result.exit_code == 0, result.output
    assert len(calls) == 1 and "连接成功" in result.output and "1024" in result.output


def test_environment_override_does_not_test_a_different_service(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIIMA_HOME", str(tmp_path))
    monkeypatch.setenv("MINIIMA_EMBEDDING_BASE_URL", "https://another.test/v1")
    def should_not_call(provider):
        pytest.fail("must not test an overridden service")
    monkeypatch.setattr(OpenAICompatibleProvider, "test_embedding", should_not_call)
    result = CliRunner().invoke(app, ["config", "qwen", "--test"], input="qwen-test-key\n")
    assert result.exit_code == 1 and "环境变量覆盖" in result.output
    assert load_settings(use_env=False).embedding_url == QWEN_EMBEDDING_BASE_URL


def test_qwen_hidden_input_is_available(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIIMA_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["config", "qwen", "--hide-key"], input="qwen-test-key\n")
    assert result.exit_code == 0 and "qwen-test-key" not in result.output


@pytest.mark.parametrize("arguments", [["config", "qwen"], ["config", "set", "--api-key"]])
def test_blank_key_is_rejected_without_saving(tmp_path, monkeypatch, arguments):
    monkeypatch.setenv("MINIIMA_HOME", str(tmp_path))
    result = CliRunner().invoke(app, arguments, input="   \n")
    assert result.exit_code == 1 and "不能为空" in result.output
    assert not (tmp_path / "config.json").exists()


def test_qwen_sdk_sends_dimensions_and_caps_batches_even_with_old_config(settings):
    settings = replace(qwen_settings(settings), embedding_batch_size=32)
    batch_sizes = []
    def handler(request):
        body = json.loads(request.content)
        assert request.method == "POST"
        assert str(request.url) == QWEN_EMBEDDING_BASE_URL + "/embeddings"
        assert request.headers["Authorization"] == "Bearer mock-embedding-key"
        assert body["model"] == QWEN_EMBEDDING_MODEL
        assert body["dimensions"] == 1024 and body["encoding_format"] == "float"
        batch_sizes.append(len(body["input"]))
        return httpx.Response(200, json={"object": "list", "model": QWEN_EMBEDDING_MODEL, "data": [
            {"object": "embedding", "index": index,
             "embedding": [float(int(text.split()[1]) + 1)] + [0.] * 1023}
            for index, text in reversed(list(enumerate(body["input"])))],
            "usage": {"prompt_tokens": 1, "total_tokens": 1}})
    vectors = sdk_provider(settings, handler).embed([f"text {i}" for i in range(41)])
    assert batch_sizes == [20, 20, 1]
    assert vectors.shape == (41, 1024) and vectors.dtype == np.float32
    np.testing.assert_array_equal(vectors[:, 0], np.arange(1, 42))


@pytest.mark.parametrize("dimension", [256, 2560])
def test_qwen_custom_dimensions_are_sent_and_validated(settings, dimension):
    settings = qwen_settings(settings, dimension=dimension)
    def handler(request):
        body = json.loads(request.content)
        assert body["dimensions"] == dimension
        return httpx.Response(200, json={"object": "list", "model": QWEN_EMBEDDING_MODEL,
            "data": [{"object": "embedding", "index": 0, "embedding": [1.] * dimension}]})
    assert sdk_provider(settings, handler).test_embedding() == dimension


def test_qwen_unsupported_dimension_is_rejected_before_input(tmp_path, monkeypatch):
    with pytest.raises(ConfigurationError, match="维度"):
        qwen_settings(Settings(), dimension=128)
    monkeypatch.setenv("MINIIMA_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["config", "qwen", "--dimension", "128"], input="qwen-test-key\n")
    assert result.exit_code == 1 and "qwen-test-key" not in result.output
    assert not (tmp_path / "config.json").exists()
