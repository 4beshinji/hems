"""
LLM Client for HEMS Brain — supports OpenAI-compatible, Ollama native, and Anthropic APIs.
"""

import json
import os
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list = field(default_factory=list)
    error: str | None = None
    # Token usage normalized to {"prompt_tokens": int, "completion_tokens": int}
    # across providers (None when the backend reports nothing). Read by the
    # cognitive loop for per-cycle cost metering (Group E).
    usage: dict | None = None


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # openai | anthropic | ollama


class LLMClient:
    def __init__(self, api_url: str = None, session=None, model: str = None, provider: str = None):
        self.api_url = api_url or os.getenv("LLM_API_URL", "http://mock-llm:8000/v1")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.session = session
        self.provider = provider or LLM_PROVIDER

    async def chat(
        self,
        messages: list,
        tools: list = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool = False,
    ) -> LLMResponse:
        if self.provider == "anthropic":
            return await self._chat_anthropic(messages, tools, temperature=temperature, max_tokens=max_tokens)
        if self.provider == "ollama":
            return await self._chat_ollama(messages, tools, temperature=temperature, max_tokens=max_tokens, think=think)
        return await self._chat_openai(messages, tools, temperature=temperature, max_tokens=max_tokens)

    async def _chat_ollama(
        self,
        messages: list,
        tools: list = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool = False,
    ) -> LLMResponse:
        """Ollama native API — supports think, num_ctx, and tool calling."""
        # Strip /v1 suffix to get base URL for native API
        base_url = self.api_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        url = f"{base_url}/api/chat"

        # Convert OpenAI tool format to Ollama format (same structure)
        ollama_tools = None
        if tools:
            ollama_tools = tools

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": think,
        }
        if ollama_tools:
            payload["tools"] = ollama_tools
        if temperature is not None:
            payload["options"] = payload.get("options", {})
            payload["options"]["temperature"] = temperature
        if max_tokens is not None:
            payload["options"] = payload.get("options", {})
            payload["options"]["num_predict"] = max_tokens

        try:
            async with self.session.post(url, json=payload, timeout=120) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return LLMResponse(error=f"Ollama HTTP {resp.status}: {text[:200]}")

                data = await resp.json()
                msg = data.get("message", {})

                tool_calls = []
                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    args = func.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    tool_calls.append(
                        {
                            "id": tc.get("id", f"call_{len(tool_calls)}"),
                            "function": {"name": func.get("name", ""), "arguments": args},
                        }
                    )

                # Ollama native reports counts at the top level, not "usage".
                usage = None
                if data.get("prompt_eval_count") is not None or data.get("eval_count") is not None:
                    usage = {
                        "prompt_tokens": data.get("prompt_eval_count"),
                        "completion_tokens": data.get("eval_count"),
                    }

                return LLMResponse(
                    content=msg.get("content", "") or "",
                    tool_calls=tool_calls,
                    usage=usage,
                )
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            return LLMResponse(error=str(e))

    async def _chat_openai(
        self, messages: list, tools: list = None, *, temperature: float | None = None, max_tokens: int | None = None
    ) -> LLMResponse:
        """OpenAI-compatible API (works with mock-llm, OpenAI)."""
        url = f"{self.api_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            async with self.session.post(url, json=payload, timeout=120) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return LLMResponse(error=f"HTTP {resp.status}: {text[:200]}")

                data = await resp.json()
                choice = data["choices"][0]
                msg = choice.get("message", {})

                tool_calls = []
                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    tool_calls.append(
                        {
                            "id": tc.get("id", ""),
                            "function": {"name": func.get("name", ""), "arguments": args},
                        }
                    )

                return LLMResponse(
                    content=msg.get("content", "") or "",
                    tool_calls=tool_calls,
                    usage=data.get("usage"),
                )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return LLMResponse(error=str(e))

    async def _chat_anthropic(
        self, messages: list, tools: list = None, *, temperature: float | None = None, max_tokens: int | None = None
    ) -> LLMResponse:
        """Anthropic Messages API."""
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        url = "https://api.anthropic.com/v1/messages"

        # Convert OpenAI format messages to Anthropic format
        system_text = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            elif msg["role"] in ("user", "assistant"):
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})
            elif msg["role"] == "tool":
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id", ""),
                                "content": msg["content"],
                            }
                        ],
                    }
                )

        # Convert OpenAI tools to Anthropic format
        anthropic_tools = []
        if tools:
            for t in tools:
                func = t.get("function", {})
                anthropic_tools.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {}),
                    }
                )

        payload = {
            "model": self.model,
            "max_tokens": max_tokens or 4096,
            "messages": anthropic_messages,
        }
        if system_text:
            payload["system"] = system_text
        if anthropic_tools:
            payload["tools"] = anthropic_tools
        if temperature is not None:
            payload["temperature"] = temperature

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            async with self.session.post(url, json=payload, headers=headers, timeout=120) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return LLMResponse(error=f"Anthropic HTTP {resp.status}: {text[:200]}")

                data = await resp.json()
                content_text = ""
                tool_calls = []

                for block in data.get("content", []):
                    if block["type"] == "text":
                        content_text += block["text"]
                    elif block["type"] == "tool_use":
                        tool_calls.append(
                            {
                                "id": block["id"],
                                "function": {"name": block["name"], "arguments": block.get("input", {})},
                            }
                        )

                # Anthropic reports input_tokens/output_tokens under "usage".
                au = data.get("usage") or {}
                usage = None
                if au:
                    usage = {
                        "prompt_tokens": au.get("input_tokens"),
                        "completion_tokens": au.get("output_tokens"),
                    }

                return LLMResponse(content=content_text, tool_calls=tool_calls, usage=usage)
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return LLMResponse(error=str(e))
