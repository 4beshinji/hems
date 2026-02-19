# CPU版を使用（LLMとのリソース競合を避けるため）
FROM voicevox/voicevox_engine:cpu-latest

# ナースロボ＿タイプＴのボイスモデル
# Speaker ID: 47 (ナースロボ＿タイプＴ)
# このボイスのみを使用

EXPOSE 50021

CMD ["/opt/voicevox_engine/run", "--host", "0.0.0.0", "--port", "50021"]
