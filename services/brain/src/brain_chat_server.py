import hmac
import os

from aiohttp import web as aio_web
from loguru import logger

from brain_constants import (
    BIOMETRIC_ENABLED,
    CHAT_MAX_ITERATIONS,
    GAS_ENABLED,
    HA_ENABLED,
    KNOWLEDGE_ENABLED,
    NEWS_ENABLED,
    OBSIDIAN_ENABLED,
    OPENCLAW_ENABLED,
    PERCEPTION_ENABLED,
    SWITCHBOT_ENABLED,
    TAPO_ENABLED,
    summarize_action,
)
from brain_utils import format_tool_call_blocks, format_tool_result_msg
from system_prompt import build_chat_system_message
from tool_registry import get_chat_tools

# Endpoints that are always accessible regardless of token configuration.
_HEALTH_PATHS = frozenset({"/health"})


@aio_web.middleware
async def brain_auth_middleware(request: aio_web.Request, handler):
    """Bearer token gate for the brain chat server.

    When ``HEMS_INTERNAL_TOKEN`` is set, every request to non-health endpoints
    must carry ``Authorization: Bearer <token>``. When the env var is unset or
    empty the middleware is a no-op (zero-config / dev mode).
    """
    token = os.getenv("HEMS_INTERNAL_TOKEN", "")
    if token and request.path not in _HEALTH_PATHS:
        auth_header = request.headers.get("Authorization", "")
        provided = auth_header.removeprefix("Bearer ").strip()
        if not hmac.compare_digest(provided, token):
            return aio_web.json_response({"error": "Unauthorized"}, status=401)
    return await handler(request)


class ChatServerMixin:
    async def _chat_health(self, request):
        return aio_web.json_response({"status": "ok"})

    async def _handle_device_control(self, request):
        """Proxy manual device control from backend UI to DeviceDispatcher.

        Action/params validation is performed by ``validate_device_control``
        (shared with the LLM path via sanitizer._validate_control_actuator)
        so both REST and LLM control requests go through identical checks.
        """
        from device_control_validator import validate_device_control

        try:
            data = await request.json()
        except Exception:
            return aio_web.json_response({"error": "Invalid JSON"}, status=400)

        if self.device_dispatcher is None:
            return aio_web.json_response(
                {"success": False, "error": "Dispatcher not initialized"},
                status=503,
            )

        from device_id_validator import is_valid_device_ref

        device_id = data.get("device_id", "")
        action = data.get("action", "")
        params = data.get("params") or {}
        if not device_id or not action:
            return aio_web.json_response(
                {"success": False, "error": "device_id and action are required"},
                status=400,
            )
        if not is_valid_device_ref(device_id):
            return aio_web.json_response(
                {"success": False, "error": f"Invalid device_id '{device_id}'"},
                status=400,
            )

        validation = validate_device_control(action, params)
        if not validation["allowed"]:
            return aio_web.json_response(
                {"success": False, "error": validation["reason"]},
                status=400,
            )

        result = await self.device_dispatcher.dispatch(device_id, action, params)
        # Invalidate cached device list so the next system prompt build refreshes.
        self._cached_devices_at = 0.0
        return aio_web.json_response(result)

    async def _handle_zigbee_permit_join(self, request):
        """Toggle Z2M pairing mode. Proxied from backend /devices/zigbee/permit_join."""
        try:
            data = await request.json()
        except Exception:
            return aio_web.json_response({"error": "Invalid JSON"}, status=400)

        if self.device_dispatcher is None:
            return aio_web.json_response(
                {"success": False, "error": "Dispatcher not initialized"},
                status=503,
            )

        enable = bool(data.get("enable", False))
        duration_s = int(data.get("duration_s", 0) or 0)
        result = self.device_dispatcher.zigbee_permit_join(enable, duration_s)
        return aio_web.json_response(result)

    async def _handle_scene_execute(self, request):
        """Execute a scene (from backend proxy or direct LLM call)."""
        try:
            data = await request.json()
        except Exception:
            return aio_web.json_response({"error": "Invalid JSON"}, status=400)

        if self.scene_executor is None:
            return aio_web.json_response(
                {"success": False, "executed": 0, "errors": ["scene_executor not ready"]},
                status=503,
            )
        actions = data.get("actions")
        name = data.get("name", "")
        if actions is not None:
            result = await self.scene_executor.execute(actions)
        elif name:
            result = await self.scene_executor.execute_by_name(name)
        else:
            return aio_web.json_response(
                {"success": False, "executed": 0, "errors": ["either 'actions' or 'name' required"]},
                status=400,
            )
        return aio_web.json_response(result)

    async def _handle_automation_evaluate(self, request):
        """Dry-run evaluate a rule's trigger; returns would_fire + reason."""
        try:
            data = await request.json()
        except Exception:
            return aio_web.json_response({"error": "Invalid JSON"}, status=400)

        if self.automation_engine is None:
            return aio_web.json_response(
                {"would_fire": False, "reason": "engine not ready"},
                status=503,
            )
        result = await self.automation_engine.evaluate_trigger(
            trigger_type=data.get("trigger_type", ""),
            trigger_config=data.get("trigger_config") or {},
        )
        return aio_web.json_response(result)

    async def _handle_chat(self, request):
        """Handle user chat query via agentic RAG with read-only tools."""
        try:
            data = await request.json()
        except Exception:
            return aio_web.json_response({"error": "Invalid JSON"}, status=400)

        history = data.get("messages", [])
        user_message = data.get("user_message", "").strip()
        if not user_message:
            return aio_web.json_response({"error": "Empty message"}, status=400)

        # Build chat-specific system prompt with world context + devices
        world_context = self.world_model.get_llm_context()
        devices_for_chat = await self._get_cached_devices()
        system_msg = build_chat_system_message(
            character=self.character,
            world_context=world_context,
            obsidian_enabled=OBSIDIAN_ENABLED,
            knowledge_enabled=KNOWLEDGE_ENABLED,
            ha_enabled=HA_ENABLED,
            biometric_enabled=BIOMETRIC_ENABLED,
            perception_enabled=PERCEPTION_ENABLED,
            news_enabled=NEWS_ENABLED,
            devices=devices_for_chat,
        )

        # Build LLM messages
        llm_messages = [system_msg]
        for msg in history:
            llm_messages.append({"role": msg["role"], "content": msg["content"]})
        llm_messages.append({"role": "user", "content": user_message})

        # Get chat tools (read-only subset)
        services_enabled = bool(self.world_model.services_state.services)
        tools = get_chat_tools(
            openclaw_enabled=OPENCLAW_ENABLED,
            services_enabled=services_enabled,
            obsidian_enabled=OBSIDIAN_ENABLED,
            ha_enabled=HA_ENABLED,
            biometric_enabled=BIOMETRIC_ENABLED,
            perception_enabled=PERCEPTION_ENABLED,
            switchbot_enabled=SWITCHBOT_ENABLED,
            news_enabled=NEWS_ENABLED,
            knowledge_enabled=KNOWLEDGE_ENABLED,
            gas_enabled=GAS_ENABLED,
            tapo_enabled=TAPO_ENABLED,
        )

        # ReAct loop (max 3 iterations for chat)
        tool_calls_log = []
        response_content = ""

        for iteration in range(1, CHAT_MAX_ITERATIONS + 1):
            response = await self.llm.chat(llm_messages, tools)
            if response.error:
                logger.warning(f"Chat LLM error: {response.error}")
                return aio_web.json_response(
                    {"error": f"LLM error: {response.error}"},
                    status=500,
                )

            if not response.tool_calls:
                response_content = response.content or ""
                break

            # Process tool calls.
            # Ollama /api/chat expects arguments as an object; OpenAI expects a JSON string.
            # Use string form only for OpenAI-compatible providers (incl. mock-llm).
            llm_provider = getattr(self.llm, "provider", "openai")
            assistant_msg = {"role": "assistant", "content": response.content or ""}
            assistant_msg["tool_calls"] = format_tool_call_blocks(llm_provider, response.tool_calls)
            llm_messages.append(assistant_msg)

            for tc in response.tool_calls:
                tool_name = tc["function"]["name"]
                arguments = tc["function"]["arguments"]
                result = await self.tool_executor.execute(tool_name, arguments)

                tool_msg = format_tool_result_msg(
                    llm_provider,
                    tool_name,
                    tc["id"],
                    str(result.get("result") or result.get("error", "")),
                )
                llm_messages.append(tool_msg)

                tool_calls_log.append(
                    {
                        "tool": tool_name,
                        "summary": summarize_action(tool_name, arguments),
                        "success": result.get("success", True),
                    }
                )

                logger.debug(
                    f"Chat tool: {tool_name}({summarize_action(tool_name, arguments)}) "
                    f"→ {'ok' if result['success'] else 'err'}"
                )

        # Stage 2 rewrite: apply character voice to the final chat response.
        # Raw response is produced by the tool-calling layer (character-free);
        # PersonaRewriter.rewrite_long preserves facts (numbers / device_ids)
        # while applying the character speaking style.
        if self.persona_rewriter is not None and response_content:
            try:
                response_content = await self.persona_rewriter.rewrite_long(
                    response_content,
                    tone="neutral",
                )
            except Exception as e:
                logger.debug(f"Chat response rewrite failed, using raw: {e}")

        # Get character name for display
        char_name = None
        if self.character:
            identity = getattr(self.character, "identity", None)
            if identity:
                char_name = getattr(identity, "name", None)

        return aio_web.json_response(
            {
                "content": response_content,
                "tool_calls": tool_calls_log,
                "character_name": char_name,
            }
        )
