"""Optional LLM report summary (Q13): facts-only JSON out, template fallback on any doubt."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.report import llm

M = "/api/missions/M-0001"
SUMMARY = "Au fost găsite 5 finding-uri; cel mai fierbinte modul are ΔT 22,4 K."


class _Reply:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


def _anthropic_reply(text: str) -> _Reply:
    return _Reply({"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]})


def _openai_reply(text: str) -> _Reply:
    return _Reply({"choices": [{"message": {"content": text}}]})


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def llm_on(monkeypatch):
    monkeypatch.setattr(settings, "report_llm", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_api_key", None)


def test_flag_off_never_calls_the_llm(client, monkeypatch):
    monkeypatch.setattr(settings, "report_llm", False)
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return _anthropic_reply(SUMMARY)

    monkeypatch.setattr(llm.httpx, "post", post)
    res = client.get(f"{M}/report")
    assert res.status_code == 200
    assert calls == []
    assert "<h2>Rezumat</h2>" not in res.text


def test_valid_summary_is_shown(client, monkeypatch, llm_on):
    calls = []

    def post(url, *, json, headers, timeout):
        calls.append(json)
        return _anthropic_reply(SUMMARY)

    monkeypatch.setattr(llm.httpx, "post", post)
    res = client.get(f"{M}/report")
    assert res.status_code == 200
    assert SUMMARY in res.text
    assert len(calls) == 1
    sent = calls[0]["messages"][0]["content"]
    assert '"delta_t_k": 22.4' in sent  # the numbers the template shows go out
    assert "crop_url" not in sent and "probs" not in sent  # nothing internal


def test_invented_number_falls_back(client, monkeypatch, llm_on):
    invented = _anthropic_reply("Există 999 finding-uri.")
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: invented)
    res = client.get(f"{M}/report")
    assert res.status_code == 200
    assert "999" not in res.text
    assert "<h2>Rezumat</h2>" not in res.text


def test_http_error_falls_back(client, monkeypatch, llm_on):
    def post(url, **kwargs):
        raise llm.httpx.TimeoutException("test timeout")

    monkeypatch.setattr(llm.httpx, "post", post)
    res = client.get(f"{M}/report")
    assert res.status_code == 200
    assert "<h2>Rezumat</h2>" not in res.text


def test_no_key_falls_back(client, monkeypatch):
    monkeypatch.setattr(settings, "report_llm", True)
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", None)

    def post(url, **kwargs):
        raise AssertionError("no HTTP call without a key")

    monkeypatch.setattr(llm.httpx, "post", post)
    res = client.get(f"{M}/report")
    assert res.status_code == 200
    assert "<h2>Rezumat</h2>" not in res.text


def test_openai_is_used_when_only_its_key_exists(client, monkeypatch):
    monkeypatch.setattr(settings, "report_llm", True)
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    calls = []

    def post(url, *, json, headers, timeout):
        calls.append((url, headers["Authorization"]))
        return _openai_reply("5 finding-uri și 22,4 K.")

    monkeypatch.setattr(llm.httpx, "post", post)
    res = client.get(f"{M}/report")
    assert res.status_code == 200
    assert calls == [(llm.OPENAI_URL, "Bearer test-key")]
    assert "5 finding-uri și 22,4 K." in res.text


def test_number_must_match_a_whole_number_in_the_payload():
    sent = '{"work_order_count": 17, "delta_t_k": 22.4}'
    assert llm._only_known_numbers("Sunt 17 ordine, ΔT 22,4 K.", sent)
    assert not llm._only_known_numbers("Sunt 7 ordine.", sent)  # substring of 17, not a fact
    assert not llm._only_known_numbers("Sunt 23 ordine.", sent)
