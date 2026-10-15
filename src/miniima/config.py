from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from urllib.parse import urlsplit

from miniima.errors import ConfigurationError


QWEN_EMBEDDING_MODEL = "qwen3.7-text-embedding"
QWEN_EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_EMBEDDING_DIMENSION = 1024
QWEN_EMBEDDING_DIMENSIONS = (256, 512, 768, 1024, 1536, 2048, 2560)
QWEN_EMBEDDING_BATCH_LIMIT = 20


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    chat_model: str = "deepseek-flash"
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_dimension: int = 0
    chunk_tokens: int = 500
    chunk_overlap: int = 80
    timeout: float = 30.0
    max_retries: int = 2
    embedding_batch_size: int = 32
    retrieval_engine: str = "cpp"
    min_score: float = 0.2
    context_tokens: int = 4000

    @property
    def embedding_url(self) -> str:
        return (self.embedding_base_url or self.base_url).rstrip("/")

    @property
    def embedding_key(self) -> str:
        if self.embedding_api_key:
            return self.embedding_api_key
        # Never send the chat key to a different embedding service implicitly.
        if self.embedding_url == self.base_url.rstrip("/"):
            return self.api_key
        return ""

    def validate(self) -> None:
        for name in ("base_url", "embedding_base_url"):
            value = getattr(self, name)
            if not value and name == "embedding_base_url":
                continue
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ConfigurationError(f"{name} 必须是有效的 HTTP(S) URL。")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ConfigurationError(f"{name} 不允许包含凭据、查询参数或片段。")
        if not self.chat_model.strip():
            raise ConfigurationError("chat_model 不能为空。")
        if self.embedding_dimension < 0:
            raise ConfigurationError("embedding_dimension 不能为负数。")
        if self.embedding_model == QWEN_EMBEDDING_MODEL and self.embedding_dimension not in QWEN_EMBEDDING_DIMENSIONS:
            raise ConfigurationError("qwen3.7-text-embedding 的维度必须为 256、512、768、1024、1536、2048 或 2560。")
        if self.chunk_tokens < 16 or not 0 <= self.chunk_overlap < self.chunk_tokens:
            raise ConfigurationError("chunk_tokens 至少为 16，重叠必须小于分块大小。")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ConfigurationError("timeout 必须是有限正数。")
        if not 0 <= self.max_retries <= 5 or self.embedding_batch_size < 1:
            raise ConfigurationError("重试次数应为 0–5，批次大小应为正数。")
        if self.retrieval_engine not in ("cpp", "numpy"):
            raise ConfigurationError("检索引擎只能是 cpp 或 numpy。")
        if not math.isfinite(self.min_score) or not -1 <= self.min_score <= 1:
            raise ConfigurationError("min_score 必须在 -1 到 1 之间。")
        if self.context_tokens < self.chunk_tokens:
            raise ConfigurationError("context_tokens 不能小于 chunk_tokens。")

    def require_chat(self) -> None:
        if not self.api_key:
            raise ConfigurationError("未配置 DeepSeek API Key，请运行 miniima config set --api-key。")

    def require_embedding(self) -> None:
        if not self.embedding_model or self.embedding_dimension < 1:
            raise ConfigurationError(
                "请运行 miniima config qwen 输入向量 API Key，自动配置 qwen3.7-text-embedding；"
                "其他模型可通过 miniima config set 配置服务地址、模型和维度。"
            )
        if not self.embedding_key:
            raise ConfigurationError("未配置向量 API Key，请运行 miniima config set --embedding-api-key。")


def qwen_settings(settings: Settings, *, base_url: str = QWEN_EMBEDDING_BASE_URL,
                  dimension: int = QWEN_EMBEDDING_DIMENSION) -> Settings:
    """Configure Qwen embeddings while preserving the separate chat settings."""
    result = replace(settings, embedding_base_url=base_url.rstrip("/"),
                     embedding_model=QWEN_EMBEDDING_MODEL, embedding_dimension=dimension,
                     embedding_batch_size=min(settings.embedding_batch_size, QWEN_EMBEDDING_BATCH_LIMIT))
    result.validate()
    return result


def data_home() -> Path:
    value = os.environ.get("MINIIMA_HOME", "").strip()
    return Path(value).expanduser().resolve() if value else Path.home() / ".miniima"


def load_settings(home: Path | None = None, *, use_env: bool = True) -> Settings:
    path = (home or data_home()) / "config.json"
    values: dict = {}
    if path.exists():
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(values, dict):
                raise ValueError("not an object")
        except (OSError, ValueError) as exc:
            raise ConfigurationError("配置文件无法读取或不是有效 JSON。") from exc
    allowed = {field.name for field in fields(Settings)}
    if set(values) - allowed:
        raise ConfigurationError("配置文件包含未知字段，请检查 config.json。")
    defaults = asdict(Settings())
    for name, default in defaults.items():
        value = values.get(name, default)
        if use_env and f"MINIIMA_{name.upper()}" in os.environ:
            value = os.environ[f"MINIIMA_{name.upper()}"]
            if value == "":
                value = default
        try:
            if isinstance(default, int):
                if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
                    raise ValueError("not an integer")
                value = int(value)
            elif isinstance(default, float):
                value = float(value)
            elif not isinstance(value, str):
                raise ValueError("not a string")
        except (ValueError, TypeError, OverflowError) as exc:
            raise ConfigurationError(f"配置项 {name} 的类型错误。") from exc
        defaults[name] = value
    result = Settings(**defaults)
    result.validate()
    return result


def save_settings(settings: Settings, home: Path | None = None) -> Path:
    settings.validate()
    root = home or data_home()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "config.json"
    fd, temporary = tempfile.mkstemp(prefix=".config-", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(asdict(settings), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path
