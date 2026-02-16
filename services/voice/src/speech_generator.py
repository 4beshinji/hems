"""
LLM-powered speech text generator — character-aware.
"""
import aiohttp
import os
import random
from loguru import logger
from models import Task

LLM_API_URL = os.getenv("LLM_API_URL", "http://mock-llm:8000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


class SpeechGenerator:
    def __init__(self, character_config: dict = None):
        self.llm_api_url = LLM_API_URL
        self.model = LLM_MODEL
        self._persona = self._build_persona(character_config or {})

    def _build_persona(self, config: dict) -> str:
        parts = []
        name = config.get("identity", {}).get("name")
        if name:
            parts.append(f"あなたの名前は「{name}」です。")
        persona = config.get("personality", {}).get("archetype")
        if persona:
            parts.append(f"性格: {persona}")
        return "\n".join(parts) if parts else ""

    async def generate_speech_text(self, task: Task) -> str:
        urgency_prefix = "【緊急】" if task.urgency >= 4 else ("至急、" if task.urgency >= 3 else "")
        prompt = f"""{self._persona}
以下のタスク情報を自然な日本語の依頼文に変換してください。70文字以内。
タイトル: {task.title}
説明: {task.description or '詳細なし'}
場所: {task.location or '場所不明'}
XP報酬: {task.xp_reward}XP
緊急度: {task.urgency}/4
エリア: {task.zone or '不明'}"""

        try:
            text = await self._call_llm(prompt)
            return urgency_prefix + text.strip()
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            loc = f"{task.zone or ''}{task.location or ''}".strip() or "指定場所"
            return f"{urgency_prefix}{loc}で{task.title}をお願いします。{task.xp_reward}XPです。"

    async def generate_completion_text(self, task: Task) -> str:
        prompt = f"""{self._persona}
以下のタスクが完了しました。完了への感謝を70文字以内で。
タイトル: {task.title}
場所: {task.location or '不明'}"""
        try:
            return (await self._call_llm(prompt)).strip()
        except Exception:
            return f"ありがとうございます！{task.title}、完了ですね。"

    async def generate_feedback(self, feedback_type: str) -> str:
        prompts = {
            "task_completed": "タスク完了への感謝を70文字以内で表現してください。",
            "task_accepted": "タスクを引き受けてくれたことへの感謝を表現してください。",
        }
        prompt = prompts.get(feedback_type, "ありがとうございますと伝えてください。")
        if self._persona:
            prompt = f"{self._persona}\n{prompt}"
        try:
            return (await self._call_llm(prompt)).strip()
        except Exception:
            return "ありがとうございます。"

    async def _call_llm(self, prompt: str) -> str:
        url = self.llm_api_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(url, json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.8,
            }) as resp:
                if resp.status != 200:
                    raise Exception(f"LLM API error {resp.status}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
