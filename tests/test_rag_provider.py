import io
import json
import urllib.error

import pytest

from services.rag import generator, config
from services.rag.assistant import ask
from services.rag.repository import load_records


def test_local_config_updates_without_stale_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_PATH", env)
    monkeypatch.setenv("LLM_MODEL", "old-model")
    env.write_text("GROQ_API_KEY=test-secret\nLLM_MODEL=first-model\n")
    assert config.settings() == {"api_key": "test-secret", "model": "first-model"}
    env.write_text("GROQ_API_KEY=test-secret\nLLM_MODEL=second-model\n")
    assert config.settings()["model"] == "second-model"


def test_http_request_headers_and_model(monkeypatch):
    monkeypatch.setattr(generator, "settings", lambda: {"api_key": "test-secret", "model": "openai/gpt-oss-20b"})
    def request(req, timeout):
        assert req.get_header("User-agent") == "FinSight/1.0"
        assert req.get_header("Authorization") == "Bearer test-secret"
        payload = json.loads(req.data)
        assert payload["model"] == "openai/gpt-oss-20b"
        assert payload["reasoning_effort"] == "low"
        assert payload["response_format"] == {"type": "json_object"}
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {
            "content": '{"recommendations": []}'}}]}).encode())
    monkeypatch.setattr(generator.urllib.request, "urlopen", request)
    assert generator.generate("MUDRA", load_records(), "en") == {"recommendations": []}


@pytest.mark.parametrize("status,code", [(401,"invalid_key"),(403,"access_denied"),
    (404,"model_unavailable"),(429,"rate_limit"),(500,"provider_error")])
def test_provider_failures_are_actionable_and_do_not_leak_secrets(monkeypatch, caplog, status, code):
    monkeypatch.setattr(generator, "settings", lambda: {"api_key": "test-secret", "model": "test"})
    def request(*args, **kwargs):
        raise urllib.error.HTTPError("https://api.groq.com", status, "test-secret", {}, io.BytesIO(b"test-secret"))
    monkeypatch.setattr(generator.urllib.request, "urlopen", request)
    result = ask("MUDRA", use_embeddings=False)
    assert result["error_code"] == code
    assert not result["recommendations"]
    assert "test-secret" not in str(result) + caplog.text


def test_truncated_generation_is_rejected(monkeypatch):
    monkeypatch.setattr(generator, "settings", lambda: {"api_key": "test-secret", "model": "test"})
    monkeypatch.setattr(generator.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(
        json.dumps({"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}).encode()))
    with pytest.raises(generator.ProviderError, match="invalid_response"):
        generator.generate("MUDRA", load_records(), "en")
