import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from typer.testing import CliRunner
import pytest

from miniima.cli import app
from miniima.config import Settings, load_settings, save_settings


@pytest.mark.parametrize("option,field", [("--api-key", "api_key"), ("--embedding-api-key", "embedding_api_key")])
@pytest.mark.parametrize("hide_key", [False, True])
def test_key_entry_visibility_redaction_and_env_override(tmp_path, monkeypatch, option, field, hide_key):
    monkeypatch.setenv("MINIIMA_HOME", str(tmp_path))
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    arguments = ["config", "set", option] + (["--hide-key"] if hide_key else [])
    result = runner.invoke(app, arguments, input="test-secret-key\n")
    assert result.exit_code == 0, result.output
    assert ("test-secret-key" in result.output) is not hide_key
    assert getattr(load_settings(), field) == "test-secret-key"
    result = runner.invoke(app, ["config", "show"])
    assert "test-secret-key" not in result.output and "已配置" in result.output
    monkeypatch.setenv("MINIIMA_CHAT_MODEL", "custom-model")
    assert load_settings().chat_model == "custom-model"
    assert load_settings(use_env=False).chat_model != "custom-model"


def test_missing_key_and_safe_separate_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIIMA_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["config", "test"])
    assert result.exit_code == 1 and "未配置" in result.output
    save_settings(Settings(api_key="chat-secret", embedding_base_url="https://another.test"), tmp_path)
    assert load_settings().embedding_key == ""


@pytest.mark.parametrize("engine", ["numpy", "cpp"])
def test_cli_new_processes_import_then_restart_and_ask(tmp_path, settings, engine):
    home = tmp_path / "data"
    save_settings(replace(settings, retrieval_engine=engine), home)
    path = tmp_path / "network.md"
    path.write_text("# TCP\n\nTCP 三次握手建立连接。", encoding="utf-8")
    project = Path(__file__).resolve().parents[1]
    env = {**os.environ, "MINIIMA_HOME": str(home), "PYTHONPATH": str(project / "src"),
           "PYTHONIOENCODING": "utf-8"}
    commands = [["init"], ["kb", "create", "网络"], ["add", str(path), "--kb", "网络"],
                ["search", "TCP", "--kb", "网络"], ["ask", "TCP 如何建立连接？", "--kb", "网络"]]
    outputs = []
    for command in commands:
        result = subprocess.run([sys.executable, str(project / "tests" / "mock_cli_runner.py"), *command],
                                env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        outputs.append(result.stdout)
    assert "导入完成" in outputs[2]
    assert "network.md" in outputs[3]
    assert "三次握手" in outputs[4] and "来源" in outputs[4] and "会话已保存" in outputs[4]
