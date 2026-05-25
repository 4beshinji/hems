import json
import time
from typing import Any

import aiohttp
from loguru import logger


class BiometricToolHandlers:
    async def _handle_get_biometrics(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get current biometric readings from world model."""
        bio = self.world_model.biometric_state
        status = {"bridge_connected": bio.bridge_connected, "provider": bio.provider}
        if bio.heart_rate.bpm is not None:
            status["heart_rate"] = {
                "bpm": bio.heart_rate.bpm,
                "zone": bio.heart_rate.zone,
                "resting_bpm": bio.heart_rate.resting_bpm,
            }
        if bio.spo2.percent is not None:
            status["spo2"] = {"percent": bio.spo2.percent}
        if bio.stress.last_update > 0:
            status["stress"] = {"level": bio.stress.level, "category": bio.stress.category}
        if bio.fatigue.last_update > 0:
            status["fatigue"] = {"score": bio.fatigue.score, "factors": bio.fatigue.factors}
        if bio.activity.last_update > 0:
            status["activity"] = {
                "steps": bio.activity.steps,
                "steps_goal": bio.activity.steps_goal,
                "calories": bio.activity.calories,
                "level": bio.activity.level,
            }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_get_sleep_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get sleep data from world model or bridge API."""
        bio = self.world_model.biometric_state
        if bio.sleep.last_update > 0:
            status = {
                "duration_minutes": bio.sleep.duration_minutes,
                "deep_minutes": bio.sleep.deep_minutes,
                "rem_minutes": bio.sleep.rem_minutes,
                "light_minutes": bio.sleep.light_minutes,
                "quality_score": bio.sleep.quality_score,
                "stage": bio.sleep.stage,
            }
            return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

        if self.biometric_url:
            try:
                async with self._session.get(
                    f"{self.biometric_url}/api/biometric/sleep",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data.get("status") != "no_data":
                        return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
            except Exception as e:
                logger.warning(f"Biometric bridge sleep query error: {e}")

        return {"success": True, "result": "睡眠データがまだありません"}

    async def _handle_get_biometric_trend(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return time-series for a biometric metric from BiometricState.history."""
        metric = (args.get("metric") or "").strip()
        if not metric:
            return {"success": False, "error": "metric is required"}
        window_hours = max(1, min(float(args.get("window_hours", 24)), 168))
        max_samples = max(10, min(int(args.get("max_samples", 100)), 500))

        bio = self.world_model.biometric_state
        history = bio.history.get(metric) if bio.history else None
        if not history:
            return {
                "success": True,
                "result": json.dumps(
                    {"metric": metric, "samples": [], "count": 0, "reason": "no history"},
                    ensure_ascii=False,
                ),
            }

        cutoff = time.time() - window_hours * 3600
        samples = [(ts, v) for ts, v in history if ts >= cutoff]
        if len(samples) > max_samples:
            step = len(samples) // max_samples
            samples = samples[::step][:max_samples]

        if samples:
            values = [v for _, v in samples]
            stats = {
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
                "first_ts": samples[0][0],
                "last_ts": samples[-1][0],
            }
        else:
            stats = {}

        return {
            "success": True,
            "result": json.dumps(
                {
                    "metric": metric,
                    "window_hours": window_hours,
                    "count": len(samples),
                    "samples": [{"ts": ts, "value": v} for ts, v in samples],
                    "stats": stats,
                },
                ensure_ascii=False,
            ),
        }

    async def _handle_get_sleep_history(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return last N days of sleep quality + duration history."""
        days = max(1, min(int(args.get("days", 7)), 14))

        bio = self.world_model.biometric_state
        quality_hist = bio.history.get("sleep_quality") if bio.history else None
        duration_hist = bio.history.get("sleep_duration") if bio.history else None

        cutoff = time.time() - days * 86400
        quality = [(ts, v) for ts, v in (quality_hist or []) if ts >= cutoff]
        duration = [(ts, v) for ts, v in (duration_hist or []) if ts >= cutoff]

        sessions = []
        for idx in range(max(len(quality), len(duration))):
            entry = {}
            if idx < len(quality):
                ts, q = quality[idx]
                entry["timestamp"] = ts
                entry["quality_score"] = q
            if idx < len(duration):
                ts, d = duration[idx]
                entry.setdefault("timestamp", ts)
                entry["duration_minutes"] = d
            sessions.append(entry)

        avg_quality = round(sum(v for _, v in quality) / len(quality), 1) if quality else None
        avg_duration = round(sum(v for _, v in duration) / len(duration), 1) if duration else None

        return {
            "success": True,
            "result": json.dumps(
                {
                    "days": days,
                    "sessions": sessions,
                    "avg_quality": avg_quality,
                    "avg_duration_minutes": avg_duration,
                    "session_count": len(sessions),
                },
                ensure_ascii=False,
            ),
        }
