"""
Ambient Speaker — periodic contextual speech generation.

Generates natural, context-aware utterances at regular intervals.
Serves dual purpose:
  1. Makes the AI character feel alive with proactive comments
  2. Exercises VoiSona TTS pipeline as an implicit health check
"""

import os
import time
from datetime import datetime

from loguru import logger

AMBIENT_INTERVAL = int(os.getenv("AMBIENT_SPEAK_INTERVAL", "300"))  # 5 min default
AMBIENT_ENABLED = os.getenv("AMBIENT_SPEAK_ENABLED", "true").lower() in ("true", "1", "yes")

# Prompt for generating ambient speech. Stage 1 is character-free — character
# voice is applied post-hoc via PersonaRewriter (passed to AmbientSpeaker below).
_AMBIENT_PROMPT = """\
家庭環境の状況に基づいて、自然な短い一言コメント（40文字以内）を日本語で生成してください。

ルール:
- 素朴で事実ベースの一言。キャラ口調や語尾装飾は付けない（後段で付与される）
- 現在の時刻、室温、湿度、天気、在室状況などから1つ選んで自然に触れる
- ユーザーへの気遣い、季節の話題、ちょっとした雑談でも可
- 同じ話題を繰り返さない（前回の話題を避ける）
- 出力はセリフのみ。説明・括弧書き・装飾語尾は不要

現在の状況:
{context}

前回の発話: {last_message}

セリフ:"""


class AmbientSpeaker:
    """Generates periodic ambient speech using LLM + world model context.

    Stage 1: raw factual utterance (this class). Stage 2: character voice via
    PersonaRewriter (provided as constructor arg; may be None in tests).
    """

    def __init__(self, llm_client, world_model, character=None, persona_rewriter=None):
        self.llm = llm_client
        self.world_model = world_model
        self.character = character
        self.persona_rewriter = persona_rewriter
        self._last_speak_time: float = 0.0
        self._last_message: str = "（まだ何も話していません）"
        self._consecutive_failures: int = 0

    @property
    def time_since_last_speak(self) -> float:
        if self._last_speak_time == 0:
            return float("inf")
        return time.monotonic() - self._last_speak_time

    def record_speak(self, message: str):
        """Record that a speak action occurred (from any source)."""
        self._last_speak_time = time.monotonic()
        self._last_message = message
        self._consecutive_failures = 0

    def should_speak(self) -> bool:
        """Check if enough time has passed for ambient speech."""
        if not AMBIENT_ENABLED:
            return False
        return self.time_since_last_speak >= AMBIENT_INTERVAL

    def _build_context(self) -> str:
        """Build a compact context string from world model."""
        now = datetime.now()
        parts = [f"時刻: {now.strftime('%H:%M')}"]

        # Time-of-day hint
        hour = now.hour
        if 5 <= hour < 10:
            parts.append("時間帯: 朝")
        elif 10 <= hour < 12:
            parts.append("時間帯: 午前")
        elif 12 <= hour < 14:
            parts.append("時間帯: お昼")
        elif 14 <= hour < 17:
            parts.append("時間帯: 午後")
        elif 17 <= hour < 20:
            parts.append("時間帯: 夕方")
        elif 20 <= hour < 23:
            parts.append("時間帯: 夜")
        else:
            parts.append("時間帯: 深夜")

        # SwitchBot / HA sensor data
        hd = self.world_model.home_devices
        for entity_id, sensor in hd.sensors.items():
            if sensor.device_class == "temperature":
                parts.append(f"室温: {sensor.value}°C")
            elif sensor.device_class == "humidity":
                parts.append(f"湿度: {sensor.value}%")

        # Weather
        w = self.world_model.physical.weather
        if w.condition:
            parts.append(f"天気: {w.condition}")
            if w.temperature:
                parts.append(f"外気温: {w.temperature}°C")

        # Biometrics (if available)
        bio = self.world_model.biometric_state
        if bio.heart_rate.bpm is not None and bio.heart_rate.bpm > 0:
            parts.append(f"心拍: {bio.heart_rate.bpm}bpm")
        if bio.fatigue.score > 0:
            parts.append(f"疲労度: {bio.fatigue.score}")

        # Occupancy
        for zone_id, zone in self.world_model.zones.items():
            if zone.occupancy.count > 0:
                parts.append(f"在室: {zone_id}")

        return "\n".join(parts)

    async def generate(self) -> dict | None:
        """Generate an ambient speak action.

        Returns a tool action dict {"tool": "speak", "args": {...}}
        or None if generation fails.
        """
        context = self._build_context()

        prompt = _AMBIENT_PROMPT.format(
            context=context,
            last_message=self._last_message,
        )

        # Stage 1: raw factual generation (no character hint in prompt).
        try:
            response = await self.llm.chat(
                [
                    {"role": "system", "content": "短い日本語のセリフを1つだけ素のまま生成してください。"},
                    {"role": "user", "content": prompt},
                ]
            )

            if response.error:
                self._consecutive_failures += 1
                logger.warning(f"Ambient speech LLM error: {response.error}")
                return None

            message = response.content.strip().strip("「」『』\"'")
            if not message or len(message) > 70:
                # Trim if too long
                message = message[:67] + "..." if message else None

            if not message:
                self._consecutive_failures += 1
                return None

            self._consecutive_failures = 0
            logger.info(f"Ambient speech generated: {message}")
            return {
                "tool": "speak",
                "args": {
                    "message": message,
                    "zone": "home",
                    "tone": "neutral",
                },
            }

        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"Ambient speech generation failed: {e}")
            return None
