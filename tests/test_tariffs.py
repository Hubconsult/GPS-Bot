"""Tests for tariff CRM helpers."""

import os

import pytest

# Ensure required settings are present before importing the module under test.
os.environ.setdefault("BOT_TOKEN", "123:ABC")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("PAY_URL_HARMONY", "https://example.com")
os.environ.setdefault("PAY_URL_REFLECTION", "https://example.com")
os.environ.setdefault("PAY_URL_TRAVEL", "https://example.com")
os.environ.setdefault("YOOKASSA_SHOP_ID", "1")
os.environ.setdefault("YOOKASSA_API_KEY", "test")

import tariffs


class DummyRedis:
    def __init__(self, value=None, should_raise=False):
        self.value = value
        self.should_raise = should_raise
        self.called_with = None

    def get(self, key):  # pragma: no cover - simple helper
        if self.should_raise:
            raise RuntimeError("redis error")
        self.called_with = key
        return self.value


def test_get_crm_access_code_returns_none_without_redis(monkeypatch):
    monkeypatch.setattr(tariffs, "r", None)
    assert tariffs.get_crm_access_code(123) is None


@pytest.mark.parametrize(
    "stored, expected",
    [("Syntera GPT 5", "Syntera GPT 5"), (b"Syntera GPT 5", "Syntera GPT 5")],
)
def test_get_crm_access_code_reads_value(monkeypatch, stored, expected):
    dummy = DummyRedis(value=stored)
    monkeypatch.setattr(tariffs, "r", dummy)

    assert tariffs.get_crm_access_code(42) == expected
    assert dummy.called_with == "user:42:tariff"


def test_get_crm_access_code_handles_errors(monkeypatch):
    dummy = DummyRedis(should_raise=True)
    monkeypatch.setattr(tariffs, "r", dummy)

    assert tariffs.get_crm_access_code(7) is None
