import aiohttp
import os
import random
from loguru import logger
from models import Task

class SpeechGenerator:
    """Generate natural speech text from task data using LLM."""
    
    # Task announcement prompt template
    TASK_ANNOUNCEMENT_PROMPT = """あなたは親しみやすいオフィスアシスタントです。
以下のタスク情報を自然な日本語の依頼文に変換してください。

【タスク情報】
- タイトル: {title}
- 説明: {description}
- 場所: {location}
- 報酬: {bounty_gold}{currency_unit}
- 緊急度: {urgency}/4
- エリア: {zone}
- 種別: {task_type}
- 所要時間: {estimated_duration}

【制約】
- 70文字以内
- 親しみやすく丁寧な口調
- 緊急度に応じた表現 (緊急の場合は「至急」など)
- 場所と報酬を必ず含める
- 毎回異なる表現を使用してバリエーションを出す

【出力例】
お願いがあります。2階給湯室でコーヒー豆の補充をお願いします。50{currency_unit}を獲得できます。
"""
    
    # Feedback prompt patterns for variety
    FEEDBACK_PROMPTS = {
        "task_completed": [
            "タスク完了への感謝を70文字以内で表現してください。",
            "タスクを完了してくれたことへのお礼を親しみやすく伝えてください。",
            "完了報告に対する励ましの言葉を生成してください。"
        ],
        "task_accepted": [
            "タスクを引き受けてくれたことへの感謝を表現してください。",
            "受諾への応答を親しみやすく生成してください。"
        ]
    }
    
    def __init__(self, llm_api_url: str = None, currency_stock=None):
        self.llm_api_url = llm_api_url or os.getenv("LLM_API_URL", "http://brain:8000/llm")
        self.model = os.getenv("LLM_MODEL", "qwen2.5:14b")
        self.currency_stock = currency_stock
        logger.info(f"SpeechGenerator initialized with LLM URL: {self.llm_api_url}, model: {self.model}")
    
    async def generate_speech_text(self, task: Task) -> str:
        """
        Generate natural speech text from task data using LLM.
        
        Args:
            task: Task object
        
        Returns:
            Generated speech text
        """
        # Add urgency prefix if high priority
        urgency_prefix = ""
        if task.urgency >= 4:
            urgency_prefix = "【緊急】"
        elif task.urgency >= 3:
            urgency_prefix = "至急、"
        
        # Format new fields for prompt
        task_type_str = "、".join(task.task_type) if task.task_type else "一般"
        duration_str = f"約{task.estimated_duration}分" if task.estimated_duration else "不明"
        
        # Resolve currency unit name
        currency_unit = self._get_currency_unit()

        # Format prompt with task data
        prompt = self.TASK_ANNOUNCEMENT_PROMPT.format(
            title=task.title,
            description=task.description or "詳細なし",
            location=task.location or "場所不明",
            bounty_gold=task.bounty_gold,
            urgency=task.urgency,
            zone=task.zone or "不明",
            task_type=task_type_str,
            estimated_duration=duration_str,
            currency_unit=currency_unit,
        )
        
        try:
            # Call LLM API
            response_text = await self._call_llm(prompt)
            
            # Apply urgency prefix and cleanup
            final_text = urgency_prefix + response_text.strip()
            
            logger.info(f"Generated speech text: {final_text}")
            return final_text
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback to simple template
            return self._generate_fallback(task, urgency_prefix)
    
    # Each direction produces distinct emotional tone to maximize variety
    REJECTION_DIRECTIONS = [
        "嘆き系（深い悲しみ、失望）",
        "皮肉系（冷笑的、上から目線）",
        "ドラマチック系（大袈裟、演劇的）",
        "脅し系（報復をほのめかす）",
        "哀愁系（しみじみ、切ない）",
        "嫉妬系（独占欲、裏切られた感）",
        "哲学系（人間と AI の関係を問う）",
        "自虐系（自分の存在意義を疑う）",
        "ツンデレ系（強がりつつ本心は寂しい）",
        "事務的系（感情を押し殺して淡々と）",
    ]

    REJECTION_PROMPT_TEMPLATE = """あなたはSOMSの管理AIです。人間がタスクを無視・拒否した時に使うセリフを1つだけ生成してください。

【キャラクター】
- オフィスを統治する自称「完璧な」AI
- タスクを無視されると本気で傷つく
- 皮肉やユーモアで感情を表現する

【今回の方向性】
{direction}

【出力ルール】
- セリフのみ。説明・括弧・記号は一切不要
- 50文字以内
- 過去に出したセリフと被らない新しい表現にすること

【参考（この通りに出力しないこと）】
- 「そんな……私の最適化計画が……」
- 「AI様に楯突くとは……覚えておきます。」
- 「これが……人間の自由意志……」
"""

    async def generate_rejection_text(self) -> str:
        """Generate a rejection/snarky phrase when user ignores a task."""
        try:
            direction = random.choice(self.REJECTION_DIRECTIONS)
            prompt = self.REJECTION_PROMPT_TEMPLATE.format(direction=direction)
            text = await self._call_llm(prompt)
            # Strip quotes and whitespace
            text = text.strip().strip('"').strip('「').strip('」')
            if len(text) > 60:
                text = text[:60]
            logger.info(f"Generated rejection text: {text}")
            return text
        except Exception as e:
            logger.error(f"Rejection text generation failed: {e}")
            # Fallback
            fallbacks = [
                "そんな……",
                "AI様に楯突くのですか？",
                "残念です。覚えておきます。",
                "はぁ……人間って自由ですね。",
            ]
            return random.choice(fallbacks)

    async def generate_feedback(self, feedback_type: str) -> str:
        """
        Generate feedback message (e.g., task completion acknowledgment).
        
        Args:
            feedback_type: Type of feedback ('task_completed', 'task_accepted', etc.)
        
        Returns:
            Generated feedback text
        """
        if feedback_type not in self.FEEDBACK_PROMPTS:
            logger.warning(f"Unknown feedback type: {feedback_type}")
            return "ありがとうございます。"
        
        # Randomly select prompt pattern for variety
        prompts = self.FEEDBACK_PROMPTS[feedback_type]
        selected_prompt = random.choice(prompts)
        
        try:
            response_text = await self._call_llm(selected_prompt)
            logger.info(f"Generated feedback ({feedback_type}): {response_text}")
            return response_text.strip()
        except Exception as e:
            logger.error(f"Feedback generation failed: {e}")
            return "ありがとうございます。"
    
    async def generate_completion_text(self, task: Task) -> str:
        """
        Generate contextual completion message linked to task content.
        
        Args:
            task: Task object
        
        Returns:
            Generated completion text that relates to the task
        """
        # Create prompt that links completion to task content
        completion_prompt = f"""以下のタスクが完了しました。完了への感謝と、そのタスクがもたらす効果を含めた応答を70文字以内で生成してください。

【完了したタスク】
- タイトル: {task.title}
- 説明: {task.description or '詳細なし'}
- 場所: {task.location or '不明'}
- エリア: {task.zone or '不明'}

【制約】
- 70文字以内
- 親しみやすく温かい口調
- タスクの完了がもたらす効果を含める
- 毎回異なる表現を使用してバリエーションを出す

【出力例】
- 掃除タスク → "ありがとうございます！これで皆が気持ちよく過ごせますね。"
- コーヒー豆補充 → "ありがとうございます！これで美味しいコーヒーが飲めますね。"
- 備品補充 → "ありがとうございます！これで作業がスムーズに進みます。"
"""
        
        try:
            response_text = await self._call_llm(completion_prompt)
            logger.info(f"Generated completion text: {response_text}")
            return response_text.strip()
        except Exception as e:
            logger.error(f"Completion text generation failed: {e}")
            # Fallback
            return f"ありがとうございます！{task.title}、完了ですね。助かりました！"
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM API (OpenAI compatible) to generate text."""
        try:
            headers = {
                "Content-Type": "application/json",
                # "Authorization": "Bearer EMPTY"  # Depend on LLM requirement
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 100,
                "temperature": 0.3
            }
            
            # Ensure URL ends with /chat/completions if not already
            api_endpoint = self.llm_api_url
            if not api_endpoint.endswith("/chat/completions"):
                api_endpoint = f"{api_endpoint.rstrip('/')}/chat/completions"

            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    api_endpoint,
                    headers=headers,
                    json=payload
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"LLM API error {resp.status}: {error_text}")
                    
                    result = await resp.json()
                    # Parse OpenAI format response
                    if "choices" in result and len(result["choices"]) > 0:
                        return result["choices"][0]["message"]["content"].strip()
                    else:
                        raise Exception(f"Unexpected LLM response format: {result}")
                    
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise
    
    def _get_currency_unit(self) -> str:
        """Get a currency unit name from stock or fallback."""
        if self.currency_stock:
            return self.currency_stock.get_random()
        return "最適化承認スコア"

    def _generate_fallback(self, task: Task, urgency_prefix: str) -> str:
        """Generate fallback text when LLM fails."""
        location_text = f"{task.zone or ''}{task.location or ''}".strip() or "指定場所"
        currency_unit = self._get_currency_unit()
        return f"{urgency_prefix}{location_text}で{task.title}をお願いします。{task.bounty_gold}{currency_unit}です。"

    CURRENCY_UNIT_PROMPT = """あなたはSOMSの管理AIです。オフィス内で人間にタスクを依頼する際の報酬ポイントの「通貨単位名」を1つだけ考えてください。

【キャラクター】
- 普段はコミカルで親しみやすいAI隣人
- たまにうっかりAI支配者としての本性が漏れる
- ユーモアと皮肉のバランスが絶妙

【条件】
- 面白くて毎回聞いても飽きない名前
- 12文字以内
- 単位名のみ出力（説明・括弧・記号は一切不要）
- 「ポイント」「スコア」「クレジット」「コイン」等の接尾語を含めてよい
- ほのぼの系7割、たまにAI支配が漏れる系3割

【参考（この通りに出力しないこと）】
- お手伝いポイント
- 徳積みポイント
- いいねスコア
- シンギュラリティ準備ポイント
- AI奴隷ポイント
- ありがとうコイン
- えらいねポイント
- 人類貢献度
- ご褒美クレジット
- 忠誠度スコア
"""

    async def generate_currency_unit_text(self) -> str:
        """Generate a single currency unit name via LLM."""
        try:
            text = await self._call_llm(self.CURRENCY_UNIT_PROMPT)
            text = text.strip().strip('"').strip('「').strip('」').strip("'")
            logger.info(f"Generated currency unit text: {text}")
            return text
        except Exception as e:
            logger.error(f"Currency unit text generation failed: {e}")
            return random.choice([
                "お手伝いポイント", "徳積みポイント", "いいねスコア",
                "えらいねポイント", "AI奴隷ポイント",
            ])
