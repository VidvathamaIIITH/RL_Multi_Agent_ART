import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from providers.azure_openai_provider import AzureOpenAIProvider


def test_repair_json_strips_markdown():
    provider = AzureOpenAIProvider()
    raw = '```json\n{"key": "value"}\n```'
    result = provider._repair_json(raw)
    assert result == '{"key": "value"}'


def test_repair_json_trailing_comma():
    provider = AzureOpenAIProvider()
    raw = '{"key": "value",}'
    result = provider._repair_json(raw)
    import json
    data = json.loads(result)
    assert data["key"] == "value"


def test_repair_json_finds_braces():
    provider = AzureOpenAIProvider()
    raw = 'Some preamble {"key": "value"} some postamble'
    result = provider._repair_json(raw)
    import json
    data = json.loads(result)
    assert data["key"] == "value"
