"""
LLM Router — routes chat() calls to different LLMClient instances
based on task_type.

Supported task types:
  "default"            → main LLM (LLM_MODEL / LLM_API_URL)
  "shopping_classify"  → default (lightweight / synchronous fallback path)
  "boot_load"          → heavy LLM (BOOT_LOAD_MODEL / BOOT_LOAD_API_URL)
                         if configured, otherwise falls back to default
  "event_classify"     → boot_load (quality matters; only runs during capsule
                         build so heavy-model latency is acceptable)
"""
import os

from llm_client import LLMClient, LLMResponse
from loguru import logger

BOOT_LOAD_MODEL = os.getenv("BOOT_LOAD_MODEL", "")
BOOT_LOAD_API_URL = os.getenv("BOOT_LOAD_API_URL", "")
BOOT_LOAD_PROVIDER = os.getenv("BOOT_LOAD_PROVIDER", "")


class LLMRouter:
    """Routes LLM calls to the appropriate client based on task_type."""

    def __init__(self, default_client: LLMClient, session=None):
        self._default = default_client
        self._boot_load: LLMClient | None = None

        # Build dedicated heavy client only when boot-load config differs from default
        if BOOT_LOAD_MODEL or BOOT_LOAD_API_URL or BOOT_LOAD_PROVIDER:
            self._boot_load = LLMClient(
                api_url=BOOT_LOAD_API_URL or default_client.api_url,
                session=session,
                model=BOOT_LOAD_MODEL or default_client.model,
                provider=BOOT_LOAD_PROVIDER or default_client.provider,
            )
            logger.info(
                "[LLMRouter] boot_load クライアント設定: provider=%s, model=%s",
                BOOT_LOAD_PROVIDER or default_client.provider,
                BOOT_LOAD_MODEL or default_client.model,
            )
        else:
            logger.debug("[LLMRouter] boot_load クライアント未設定: デフォルトモデルを使用")

    async def chat(
        self,
        messages: list,
        tools: list = None,
        *,
        task_type: str = "default",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Route to the appropriate LLMClient and call chat()."""
        use_boot_load = task_type in ("boot_load", "event_classify")
        is_boot_load = use_boot_load and self._boot_load is not None
        client = self._boot_load if is_boot_load else self._default
        # Enable thinking for boot_load: time budget is generous and quality matters
        think = is_boot_load and client.provider == "ollama"
        return await client.chat(
            messages, tools,
            temperature=temperature,
            max_tokens=max_tokens,
            think=think,
        )
