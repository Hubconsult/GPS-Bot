from __future__ import annotations

import types

import unittest

from openai_adapter import (
    call_chat_completion,
    coerce_content_to_text,
    prepare_responses_input,
)


class _DummyResponse:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def model_dump(self):
        data = {}
        for key, value in self.__dict__.items():
            data[key] = value
        return data


class CallChatCompletionTests(unittest.TestCase):
    def test_uses_responses_api_when_available(self):
        messages = [{"role": "user", "content": "Привет"}]

        class DummyClient:
            def __init__(self):
                self.responses_called = False
                self.chat_called = False
                self.responses = types.SimpleNamespace(create=self._responses_create)
                self.chat = types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=self._chat_create)
                )

            def _responses_create(self, **kwargs):
                self.responses_called = True
                return _DummyResponse(output_text="Ответ из responses")

            def _chat_create(self, **kwargs):
                self.chat_called = True
                return _DummyResponse(
                    choices=[types.SimpleNamespace(message={"content": "Ответ из chat"})]
                )

        client = DummyClient()
        text, _ = call_chat_completion(client, "gpt-test", messages)

        self.assertEqual(text, "Ответ из responses")
        self.assertTrue(client.responses_called)
        self.assertFalse(client.chat_called)

    def test_falls_back_to_chat_completions(self):
        messages = [{"role": "user", "content": "Привет"}]

        class DummyClient:
            def __init__(self):
                self.responses_called = False
                self.chat_called = False
                self.responses = types.SimpleNamespace(create=self._responses_create)
                self.chat = types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=self._chat_create)
                )

            def _responses_create(self, **kwargs):
                self.responses_called = True
                raise RuntimeError("responses unavailable")

            def _chat_create(self, **kwargs):
                self.chat_called = True
                return _DummyResponse(
                    choices=[types.SimpleNamespace(message={"content": "Ответ из chat"})]
                )

        client = DummyClient()
        text, _ = call_chat_completion(client, "gpt-test", messages)

        self.assertEqual(text, "Ответ из chat")
        self.assertTrue(client.responses_called)
        self.assertTrue(client.chat_called)


class PrepareResponsesInputTests(unittest.TestCase):
    def test_converts_non_list_content_to_strings(self):
        messages = [
            {"role": "system", "content": "rule"},
            {"role": "user", "content": 123},
            {"role": "assistant", "content": ["already", " list"]},
        ]

        prepared = prepare_responses_input(messages)

        self.assertEqual(
            prepared,
            [
                {"role": "system", "content": "rule"},
                {"role": "user", "content": "123"},
                {"role": "assistant", "content": ["already", " list"]},
            ],
        )


class CoerceContentToTextTests(unittest.TestCase):
    def test_skips_reasoning_objects(self):
        class DummyItem:
            def __init__(self, type_: str, text: str | None = None, content: str | None = None):
                self.type = type_
                self.text = text
                self.content = content

        reasoning = DummyItem("reasoning", text="internal", content="internal")
        visible = DummyItem("output_text", text="Visible answer")

        result = coerce_content_to_text([reasoning, visible])

        self.assertEqual(result, "Visible answer")

    def test_skips_reasoning_mappings(self):
        payload = [
            {"type": "reasoning", "text": "internal"},
            {"type": "output_text", "text": "Visible answer"},
        ]

        result = coerce_content_to_text(payload)

        self.assertEqual(result, "Visible answer")


if __name__ == "__main__":  # pragma: no cover - direct execution
    unittest.main()
