"""Offline unit tests for OpenAI-compatible (vLLM) backend URL construction.

No GPU / live vLLM required — httpx is mocked.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

MODELS = Path(__file__).resolve().parents[2] / "packages" / "models"
if str(MODELS) not in sys.path:
    sys.path.insert(0, str(MODELS))

from inference.backends import OpenAICompatBackend, build_backend
from inference.contracts import InferenceRequest


def test_openai_compat_builds_with_url_and_api_key():
    b = OpenAICompatBackend(
        "http://localhost:8008/v1",
        api_key="EMPTY",
        default_model="Qwen/Qwen2.5-0.5B-Instruct",
    )
    assert b.name == "openai_compat"
    assert b.simulated is False
    assert b.base_url == "http://localhost:8008/v1"
    assert b.api_key == "EMPTY"
    assert b.default_model == "Qwen/Qwen2.5-0.5B-Instruct"


def test_chat_url_when_base_ends_with_v1():
    b = OpenAICompatBackend("http://localhost:8008/v1")
    assert b._url("/chat/completions") == "http://localhost:8008/v1/chat/completions"
    assert b._url("/models") == "http://localhost:8008/v1/models"


def test_chat_url_when_base_is_bare_host():
    b = OpenAICompatBackend("http://localhost:8008")
    assert b._url("/chat/completions") == "http://localhost:8008/v1/chat/completions"
    assert b._url("/models") == "http://localhost:8008/v1/models"


def test_base_url_trailing_slash_stripped():
    b = OpenAICompatBackend("http://localhost:8008/v1/")
    assert b.base_url == "http://localhost:8008/v1"
    assert b._url("/chat/completions") == "http://localhost:8008/v1/chat/completions"


def test_build_backend_remote_uses_openai_compat():
    b = build_backend(
        mode="remote",
        model_id="Qwen/Qwen2.5-0.5B-Instruct",
        vllm_base_url="http://localhost:8008/v1",
        vllm_api_key="secret-key",
    )
    assert isinstance(b, OpenAICompatBackend)
    assert b.base_url == "http://localhost:8008/v1"
    assert b.api_key == "secret-key"
    assert b.default_model == "Qwen/Qwen2.5-0.5B-Instruct"


def test_generate_posts_to_chat_completions_url():
    """Mock httpx: ensure POST goes to .../v1/chat/completions with Bearer auth."""
    captured: dict = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 1,
                    "total_tokens": 4,
                },
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp()

    backend = OpenAICompatBackend(
        "http://localhost:8008/v1",
        api_key="EMPTY",
        default_model="Qwen/Qwen2.5-0.5B-Instruct",
    )
    req = InferenceRequest(
        model_id="Qwen/Qwen2.5-0.5B-Instruct",
        prompt="Say ok",
        max_tokens=8,
        temperature=0.0,
    )

    with patch("httpx.AsyncClient", _Client):
        resp = asyncio.run(backend.generate(req, evidence="soil test N low"))

    assert captured["url"] == "http://localhost:8008/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer EMPTY"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["json"]["model"] == "Qwen/Qwen2.5-0.5B-Instruct"
    assert captured["json"]["stream"] is False
    assert captured["json"]["max_tokens"] == 8
    messages = captured["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "soil test" in messages[1]["content"]
    assert "Say ok" in messages[1]["content"]
    assert resp.completion == "ok"
    assert resp.model_id == "Qwen/Qwen2.5-0.5B-Instruct"
    assert resp.usage["total_tokens"] == 4
    assert resp.warnings is None


def test_generate_bare_host_posts_with_v1_prefix():
    captured: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
                "usage": {},
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            return _Resp()

    backend = OpenAICompatBackend("http://vllm:8000", api_key="k", default_model="m")
    req = InferenceRequest(model_id="m", prompt="x")
    with patch("httpx.AsyncClient", _Client):
        asyncio.run(backend.generate(req))
    assert captured["url"] == "http://vllm:8000/v1/chat/completions"


def test_health_check_hits_models_endpoint():
    backend = OpenAICompatBackend("http://localhost:8008/v1", api_key="EMPTY")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("httpx.get", return_value=mock_resp) as get:
        assert backend.health_check() is True
        get.assert_called_once()
        args, kwargs = get.call_args
        assert args[0] == "http://localhost:8008/v1/models"
        assert kwargs["headers"]["Authorization"] == "Bearer EMPTY"


def test_health_check_false_on_error():
    backend = OpenAICompatBackend("http://localhost:8008/v1")
    with patch("httpx.get", side_effect=OSError("down")):
        assert backend.health_check() is False
