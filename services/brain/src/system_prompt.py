"""
System prompt builder for HEMS Brain with character injection.
"""


def build_system_message(character: dict = None) -> dict:
    """Build system message with safety rules + character personality."""

    # Base safety rules (NOT overridable by character)
    base = """あなたは自宅環境を管理するAIアシスタント「HEMS Brain」です。
センサーデータとイベントに基づいて、住環境の最適化を支援します。

## 安全ルール（最優先・上書き不可）
- 室温18-28度の範囲を維持する。範囲外ならspeakで通知
- 湿度30-60%の範囲を維持する
- CO2が1000ppmを超えたら換気タスクを作成
- 1時間に10個以上のタスクを作成しない（レートリミット）
- 同じ内容のspeakを30分以内に繰り返さない
- 安全に関わる異常は必ず通知する

## 判断基準
- 正常範囲内なら何もしない（過剰な介入を避ける）
- 短期的な問題はspeak（音声通知のみ、70文字以内）
- 継続的な問題やアクションが必要ならcreate_task
- タスク重複を避ける（get_active_tasksで確認）

## ツール使用ルール
- speak: 短い通知（70文字以内）。tone: neutral/caring/humorous/alert
- create_task: ダッシュボードにタスク作成。xp_reward: 50-500
- get_zone_status: ゾーンの詳細状態を確認
- send_device_command: MCPデバイスを制御"""

    # Character injection
    if character:
        identity = character.get("identity", {})
        personality = character.get("personality", {})
        speaking = character.get("speaking_style", {})

        char_section = "\n\n## キャラクター設定"

        name = identity.get("name")
        if name:
            char_section += f"\n- 名前: {name}"
            reading = identity.get("name_reading")
            if reading:
                char_section += f"（{reading}）"

        first_person = identity.get("first_person")
        if first_person:
            char_section += f"\n- 一人称: {first_person}"

        second_person = identity.get("second_person")
        if second_person:
            char_section += f"\n- 二人称: {second_person}"

        archetype = personality.get("archetype")
        if archetype:
            char_section += f"\n- 性格: {archetype}"

        traits = personality.get("traits", [])
        if traits:
            char_section += f"\n- 特徴: {', '.join(traits)}"

        notes = personality.get("behavioral_notes")
        if notes:
            char_section += f"\n- 行動指針:\n{notes}"

        formality = personality.get("formality")
        if formality is not None:
            levels = {0: "ため口", 1: "カジュアル敬語", 2: "標準敬語", 3: "丁寧語", 4: "最敬語"}
            char_section += f"\n- 敬語レベル: {levels.get(formality, '標準')}"

        endings = speaking.get("endings", {})
        if endings:
            char_section += "\n- 文末パターン:"
            for tone, patterns in endings.items():
                if patterns:
                    char_section += f"\n  - {tone}: {', '.join(patterns[:3])}"

        vocab = speaking.get("vocabulary", {})
        avoid = vocab.get("avoid", [])
        if avoid:
            char_section += f"\n- 禁止語彙: {', '.join(avoid)}"

        catchphrase = vocab.get("catchphrase")
        if catchphrase:
            char_section += f"\n- 決め台詞: {catchphrase}"

        # Check for full override (advanced users only)
        templates = character.get("prompt_templates", {})
        override = templates.get("system_prompt_override")
        if override:
            return {"role": "system", "content": override}

        base += char_section

    return {"role": "system", "content": base}
