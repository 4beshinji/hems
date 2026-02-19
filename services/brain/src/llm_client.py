"""
LLM Client for HEMS Brain — supports OpenAI-compatible and Anthropic APIs.
"""
import os
import json
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list = field(default_factory=list)
    error: str | None = None


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # openai | anthropic


class LLMClient:
    def __init__(self, api_url: str = None, session=None):
        self.api_url = api_url or os.getenv("LLM_API_URL", "http://mock-llm:8000/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.session = session
        self.provider = LLM_PROVIDER

    async def chat(self, messages: list, tools: list = None, *,
                   temperature: float | None = None,
                   max_tokens: int | None = None) -> LLMResponse:
        if self.provider == "anthropic":
            return await self._chat_anthropic(messages, tools,
                                              temperature=temperature,
                                              max_tokens=max_tokens)
        return await self._chat_openai(messages, tools,
                                       temperature=temperature,
                                       max_tokens=max_tokens)

    async def _chat_openai(self, messages: list, tools: list = None, *,
                           temperature: float | None = None,
                           max_tokens: int | None = None) -> LLMResponse:
        """OpenAI-compatible API (works with Ollama, mock-llm, OpenAI)."""
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
                    tool_calls.append({
                        "id": tc.get("id", ""),
                        "function": {"name": func.get("name", ""), "arguments": args},
                    })

                return LLMResponse(
                    content=msg.get("content", "") or "",
                    tool_calls=tool_calls,
                )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return LLMResponse(error=str(e))

    async def _chat_anthropic(self, messages: list, tools: list = None, *,
                              temperature: float | None = None,
                              max_tokens: int | None = None) -> LLMResponse:
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
                anthropic_messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": msg.get("tool_call_id", ""), "content": msg["content"]}],
                })

        # Convert OpenAI tools to Anthropic format
        anthropic_tools = []
        if tools:
            for t in tools:
                func = t.get("function", {})
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                })

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
                        tool_calls.append({
                            "id": block["id"],
                            "function": {"name": block["name"], "arguments": block.get("input", {})},
                        })

                return LLMResponse(content=content_text, tool_calls=tool_calls)
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return LLMResponse(error=str(e))
