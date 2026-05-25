import json
import time
from typing import Any

import aiohttp


class PerceptionToolHandlers:
    async def _handle_get_perception_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get camera-based occupancy and activity data from world model."""
        zones_data = {}
        for zone_id, zone in self.world_model.zones.items():
            occ = zone.occupancy
            if occ.last_update > 0:
                zones_data[zone_id] = {
                    "person_count": occ.count,
                    "activity_level": occ.activity_level,
                    "activity_class": occ.activity_class,
                    "posture": occ.posture,
                    "posture_status": occ.posture_status,
                    "posture_duration_sec": occ.posture_duration_sec,
                    "last_update": occ.last_update,
                }
        if not zones_data:
            return {"success": True, "result": "カメラデータがまだありません"}
        return {"success": True, "result": json.dumps({"zones": zones_data}, ensure_ascii=False)}

    async def _handle_describe_scene(self, args: dict[str, Any]) -> dict[str, Any]:
        """Analyze camera scene via VLM (on-demand). Uses cached data if recent."""
        zone_id = args.get("zone_id", "")
        custom_prompt = args.get("prompt", "")

        if not custom_prompt:
            for zid, zone in self.world_model.zones.items():
                if zone_id and zid != zone_id:
                    continue
                occ = zone.occupancy
                if occ.vlm_last_update > 0 and time.time() - occ.vlm_last_update < 60:
                    data = {
                        "zone": zid,
                        "description": occ.scene_description,
                        "objects": occ.scene_objects,
                        "scene_type": occ.scene_type,
                        "anomalies": occ.scene_anomalies,
                        "cached": True,
                    }
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}

        if not self.perception_url:
            return {"success": False, "error": "Perception bridge not configured"}
        try:
            async with self._session.post(
                f"{self.perception_url}/api/perception/vlm/analyze",
                json={
                    "zone_id": zone_id or None,
                    "prompt": custom_prompt or None,
                },
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    if data.get("error"):
                        return {"success": False, "error": data["error"]}
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except TimeoutError:
            return {"success": False, "error": "VLM分析がタイムアウトしました"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_list_scene_objects(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return unique objects seen in the zone's VLM history within the time window."""
        zone_id = args.get("zone_id", "")
        if not zone_id:
            return {"success": False, "error": "zone_id required"}
        since_minutes = int(args.get("since_minutes", 60) or 60)
        since_minutes = max(1, min(since_minutes, 60))
        cutoff = time.time() - since_minutes * 60

        zone = self.world_model.zones.get(zone_id)
        if not zone:
            return {"success": True, "result": json.dumps({"zone": zone_id, "objects": []}, ensure_ascii=False)}

        seen: dict[str, dict[str, Any]] = {}
        for snap in zone.occupancy.vlm_history:
            if snap.timestamp < cutoff:
                continue
            for obj in snap.objects:
                entry = seen.setdefault(obj, {"count": 0, "last_seen": 0})
                entry["count"] += 1
                entry["last_seen"] = max(entry["last_seen"], snap.timestamp)
        objects = sorted(
            (
                {"name": name, "count": info["count"], "last_seen_ago_sec": int(time.time() - info["last_seen"])}
                for name, info in seen.items()
            ),
            key=lambda x: (-x["count"], x["last_seen_ago_sec"]),
        )
        return {
            "success": True,
            "result": json.dumps(
                {"zone": zone_id, "since_minutes": since_minutes, "objects": objects[:30]},
                ensure_ascii=False,
            ),
        }

    async def _handle_get_scene_timeline(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the VLM scene history (latest 10) as a time-ordered list."""
        zone_id = args.get("zone_id", "")
        if not zone_id:
            return {"success": False, "error": "zone_id required"}
        zone = self.world_model.zones.get(zone_id)
        if not zone or not zone.occupancy.vlm_history:
            return {"success": True, "result": json.dumps({"zone": zone_id, "timeline": []}, ensure_ascii=False)}

        now = time.time()
        timeline = [
            {
                "age_sec": int(now - s.timestamp),
                "description": s.description[:200],
                "scene_type": s.scene_type,
                "objects": s.objects[:8],
                "anomalies": s.anomalies[:3],
                "tier": s.tier,
            }
            for s in zone.occupancy.vlm_history
        ]
        return {
            "success": True,
            "result": json.dumps({"zone": zone_id, "timeline": timeline}, ensure_ascii=False),
        }

    async def _handle_list_cameras(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.perception_url:
            return {"success": False, "error": "Perception bridge not configured"}
        try:
            async with self._session.get(
                f"{self.perception_url}/api/perception/cameras",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_vlm_status(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.perception_url:
            return {"success": False, "error": "Perception bridge not configured"}
        try:
            async with self._session.get(
                f"{self.perception_url}/api/perception/vlm/status",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {"success": True, "result": json.dumps(data, ensure_ascii=False)}
                return {"success": False, "error": data.get("detail", f"HTTP {resp.status}")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_get_activity_history(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return per-zone activity/scene snapshots from world_model in chronological order."""
        zone_id = args.get("zone_id", "")
        if not zone_id:
            return {"success": False, "error": "zone_id required"}
        limit = max(1, min(int(args.get("limit", 10)), 30))

        zone = self.world_model.zones.get(zone_id)
        if not zone:
            return {"success": True, "result": json.dumps({"zone": zone_id, "snapshots": []}, ensure_ascii=False)}

        now = time.time()
        snapshots = [
            {
                "age_sec": int(now - s.timestamp),
                "scene_type": s.scene_type,
                "anomalies": s.anomalies[:3],
                "object_count": len(s.objects),
                "description": s.description[:120],
                "tier": s.tier,
            }
            for s in list(zone.occupancy.vlm_history)[-limit:]
        ]
        return {
            "success": True,
            "result": json.dumps(
                {
                    "zone": zone_id,
                    "current_activity_level": zone.occupancy.activity_level,
                    "current_posture": zone.occupancy.posture,
                    "snapshots": snapshots,
                },
                ensure_ascii=False,
            ),
        }
