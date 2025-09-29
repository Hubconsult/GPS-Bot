"""Utilities to normalize OpenAI SDK responses across OpenAI SDK versions."""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

_SUPPRESSED_CONTENT_TYPES = {
    "reasoning",
    "annotation",
    "annotations",
    "refusal",
    "safety",
}


def _detect_content_type(value: Any) -> str:
    """Return a lower-cased content type if present on the object or mapping."""

    type_attr = getattr(value, "type", None)
    if isinstance(type_attr, str):
        return type_attr.lower()

    if isinstance(value, dict):
        type_value = value.get("type")
        if isinstance(type_value, str):
            return type_value.lower()

    return ""


def coerce_content_to_text(content: Any) -> str:
    """Coerce the various SDK content containers to plain text."""

    if content is None:
        return ""

    if _detect_content_type(content) in _SUPPRESSED_CONTENT_TYPES:
        return ""

    if isinstance(content, str):
        return content

    text_attr = getattr(content, "text", None)
    if isinstance(text_attr, str):
        return text_attr
    if text_attr is not None:
        return coerce_content_to_text(text_attr)

    for attr_name in ("content", "value"):
        attr_value = getattr(content, attr_name, None)
        if attr_value is not None and attr_value is not content:
            return coerce_content_to_text(attr_value)

    if isinstance(content, list):
        parts = [coerce_content_to_text(item) for item in content]
        return "".join(parts)

    if isinstance(content, dict):
        if _detect_content_type(content) in _SUPPRESSED_CONTENT_TYPES:
            return ""
        if isinstance(content.get("text"), str):
            return content.get("text", "")
        if isinstance(content.get("output_text"), str):
            return content.get("output_text", "")
        if "content" in content:
            return coerce_content_to_text(content["content"])
        if "value" in content:
            return coerce_content_to_text(content["value"])
        if "arguments" in content:
            return coerce_content_to_text(content["arguments"])
        if "text" in content:
            return coerce_content_to_text(content.get("text"))

    return str(content)


def extract_message_text(message: Any) -> str:
    if message is None:
        return ""

    if isinstance(message, dict):
        return coerce_content_to_text(message.get("content"))

    content = getattr(message, "content", None)
    text = coerce_content_to_text(content)
    if text:
        return text

    contents = getattr(message, "contents", None)
    text = coerce_content_to_text(contents)
    if text:
        return text

    return coerce_content_to_text(getattr(message, "text", ""))


def extract_choice_text(choice: Any) -> str:
    if choice is None:
        return ""

    message = getattr(choice, "message", None)
    text = extract_message_text(message)
    if text:
        return text

    content = getattr(choice, "content", None)
    text = coerce_content_to_text(content)
    if text:
        return text

    if isinstance(choice, dict):
        if "message" in choice:
            text = extract_message_text(choice.get("message"))
            if text:
                return text
        if "content" in choice:
            text = coerce_content_to_text(choice.get("content"))
            if text:
                return text
        if "delta" in choice:
            text = coerce_content_to_text(choice.get("delta"))
            if text:
                return text

    return ""


def _extract_from_dict_like_response(response: Dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return ""

    if "output_text" in response:
        text = coerce_content_to_text(response.get("output_text"))
        if text:
            return text

    if "output" in response:
        text = coerce_content_to_text(response.get("output"))
        if text:
            return text

    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        text = extract_choice_text(choices[0])
        if text:
            return text

    return ""


def extract_response_text(response: Any) -> str:
    """Extract a plain text answer from any OpenAI SDK response object."""

    if response is None:
        return ""

    text = coerce_content_to_text(getattr(response, "output_text", None))
    if text:
        return text

    text = coerce_content_to_text(getattr(response, "output", None))
    if text:
        return text

    text = coerce_content_to_text(getattr(response, "content", None))
    if text:
        return text

    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        text = extract_choice_text(choices[0])
        if text:
            return text

    if isinstance(response, dict):
        text = _extract_from_dict_like_response(response)
        if text:
            return text

    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except Exception:  # pragma: no cover - defensive
            dumped = None
        if dumped:
            text = extract_response_text(dumped)
            if text:
                return text

    return coerce_content_to_text(response)


def prepare_responses_input(messages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, list):
            prepared.append({"role": role, "content": content})
        else:
            prepared.append({"role": role, "content": str(content)})
    return prepared


def dump_response_for_log(response: Any) -> Any:
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump()
        except Exception:  # pragma: no cover - defensive
            pass
    return response


def call_chat_completion(
    client: Any,
    model: str,
    messages: Sequence[Dict[str, Any]],
    *,
    max_tokens: int | None = None,
    stream: bool = False,
) -> Tuple[str, Any]:
    """Call the OpenAI SDK using either the Responses or Chat Completions API."""

    errors: List[Exception] = []

    responses_api = getattr(client, "responses", None)
    if responses_api and hasattr(responses_api, "create"):
        kwargs: Dict[str, Any] = {"model": model, "input": prepare_responses_input(messages)}
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        try:
            response = responses_api.create(**kwargs)
            return extract_response_text(response), response
        except Exception as exc:  # pragma: no cover - depends on SDK behaviour
            errors.append(exc)

    chat_api = getattr(getattr(client, "chat", None), "completions", None)
    if chat_api and hasattr(chat_api, "create"):
        kwargs = {"model": model, "messages": list(messages)}
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        if stream is not None:
            kwargs["stream"] = stream
        try:
            response = chat_api.create(**kwargs)
            return extract_response_text(response), response
        except Exception as exc:
            errors.append(exc)

    if errors:
        raise errors[-1]

    raise RuntimeError("OpenAI client does not expose a compatible chat interface")
