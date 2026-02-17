"""
System prompt builder for HEMS Brain with character injection.
"""
from dataclasses import fields as dc_fields, asdict


def build_system_message(character=None, openclaw_enabled: bool = False,
                         services_enabled: bool = False) -> dict:
    """Build system message with safety rules + character personality.

    Args:
        character: CharacterConfig dataclass or None.
        openclaw_enabled: Whether OpenClaw PC tools are available.
        services_enabled: Whether service monitor tools are available.
    """

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

    if openclaw_enabled:
        base += """

## PCツール（OpenClaw連携）
- get_pc_status: CPU/メモリ/GPU/ディスク情報を取得。include_processes=trueでプロセス一覧も取得
- run_pc_command: ホストPCでシェルコマンドを実行。ファイル確認、アプリ起動等に使用
- control_browser: ブラウザ操作（navigate/eval/get_url/get_title）
- send_pc_notification: デスクトップ通知を送信

## PC安全ルール
- rm -rf、mkfs、shutdown等の破壊的コマンドは禁止
- GPU温度85度以上は緊急通知する
- ディスク90%以上は整理タスクを作成する
- PCメトリクスが取得できない場合はブリッジの接続状態を確認する"""

    if services_enabled:
        base += """

## サービスモニター
- get_service_status: 外部サービスの状態を取得（Gmail未読数、GitHub通知等）
- service_nameを省略すると全サービスの状態を一覧取得
- 未読数が増加した場合はspeakで通知を検討する
- サービスエラーが続く場合はcreate_taskで確認タスクを作成する"""

    # Character injection
    if character:
        identity = getattr(character, "identity", None)
        personality = getattr(character, "personality", None)
        speaking = getattr(character, "speaking_style", None)

        char_section = "\n\n## キャラクター設定"

        if identity:
            name = getattr(identity, "name", None)
            if name:
                char_section += f"\n- 名前: {name}"
                reading = getattr(identity, "name_reading", None)
                if reading:
                    char_section += f"（{reading}）"

            first_person = getattr(identity, "first_person", None)
            if first_person:
                char_section += f"\n- 一人称: {first_person}"

            second_person = getattr(identity, "second_person", None)
            if second_person:
                char_section += f"\n- 二人称: {second_person}"

        if personality:
            archetype = getattr(personality, "archetype", None)
            if archetype:
                char_section += f"\n- 性格: {archetype}"

            traits = getattr(personality, "traits", [])
            if traits:
                char_section += f"\n- 特徴: {', '.join(traits)}"

            notes = getattr(personality, "behavioral_notes", None)
            if notes:
                char_section += f"\n- 行動指針:\n{notes}"

            formality = getattr(personality, "formality", None)
            if formality is not None:
                levels = {0: "ため口", 1: "カジュアル敬語", 2: "標準敬語", 3: "丁寧語", 4: "最敬語"}
                char_section += f"\n- 敬語レベル: {levels.get(formality, '標準')}"

        if speaking:
            endings = getattr(speaking, "endings", None)
            if endings:
                char_section += "\n- 文末パターン:"
                for f in dc_fields(endings):
                    patterns = getattr(endings, f.name, [])
                    if patterns:
                        char_section += f"\n  - {f.name}: {', '.join(patterns[:3])}"

            vocab = getattr(speaking, "vocabulary", None)
            if vocab:
                avoid = getattr(vocab, "avoid", [])
                if avoid:
                    char_section += f"\n- 禁止語彙: {', '.join(avoid)}"

                catchphrase = getattr(vocab, "catchphrase", None)
                if catchphrase:
                    char_section += f"\n- 決め台詞: {catchphrase}"

        # Check for full override (advanced users only)
        templates = getattr(character, "prompt_templates", None)
        if templates:
            override = getattr(templates, "system_prompt_override", None)
            if override:
                return {"role": "system", "content": override}

        base += char_section

    return {"role": "system", "content": base}
