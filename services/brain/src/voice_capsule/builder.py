"""CapsuleBuilder — orchestrates clip planning → synth → persist.

Called from BootLoadManager after the briefing is generated. The builder
produces a day-keyed manifest and pushes it through:

  1. clip_planner.plan_day  → ClipSpec list (+ generic_bank)
  2. transcript_writer      → PersonaRewriter overlays persona voice
  3. voice-service          → batch-synthesize → deterministic MP3 URLs
  4. persist.push_manifest  → backend VoiceCapsule table upsert
  5. MQTT notify            → ``hems/voice-capsule/ready`` (phone trigger)

The output is a dict that matches :class:`schemas.VoiceCapsuleManifest` —
deliberately JSON-shaped so the backend receives it verbatim.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger

from .generic_bank import GenericSpec, default_bank
from .persist import push_manifest
from .transcript_writer import TranscriptWriter

if TYPE_CHECKING:
    import aiohttp
    import paho.mqtt.client as mqtt
    from annotator import EventClassifier
    from persona_rewriter import PersonaRewriter


@dataclass
class ClipSpec:
    """Planner output — feeds both the TTS batch call and the manifest."""
    id: str
    trigger_kind: str              # "time" | "pre_event" | "geofence" | "biometric_threshold"
    tone: str
    transcript_seed: str           # pre-PersonaRewriter raw line
    trigger_at_ts: int | None = None
    event_ref: str | None = None
    event_offset_min: int | None = None   # lead time in minutes for pre_event triggers
    tags: list[str] = field(default_factory=list)
    priority: int = 5

    # Geofence trigger payload (only populated for trigger_kind="geofence").
    place_id: int | None = None
    place_category: str | None = None
    place_lat: float | None = None
    place_lon: float | None = None
    place_radius_m: int | None = None
    cooldown_min: int | None = None

    # Biometric-threshold payload (trigger_kind="biometric_threshold").
    biometric_metric: str | None = None        # heart_rate | stress | fatigue | ...
    biometric_op: str | None = None            # "gt" | "lt"
    biometric_value: float | None = None

    # Populated by the builder after transcript/synth.
    transcript: str | None = None
    audio_url: str | None = None


class CapsuleBuilder:
    def __init__(
        self,
        *,
        session: "aiohttp.ClientSession",
        voice_service_url: str,
        backend_url: str,
        api_key: str,
        persona_rewriter: "PersonaRewriter | None" = None,
        mqtt_client: "mqtt.Client | None" = None,
        character_version: str | None = None,
        event_classifier: "EventClassifier | None" = None,
    ):
        self.session = session
        self.voice_service_url = voice_service_url.rstrip("/")
        self.backend_url = backend_url.rstrip("/")
        self.api_key = api_key
        self.writer = TranscriptWriter(persona_rewriter)
        self.mqtt_client = mqtt_client
        self.character_version = character_version
        self.event_classifier = event_classifier

    async def build_daily_capsule(
        self,
        date: str,
        *,
        world_model,
        wake_ts: float | None = None,
    ) -> dict | None:
        """Entry point called by BootLoadManager. ``date`` is YYYY-MM-DD."""
        from .clip_planner import plan_day  # deferred to avoid circular import

        places = await self._fetch_frequent_places()
        pending_shopping = await self._fetch_pending_shopping()

        clips = await plan_day(
            date=date, wake_ts=wake_ts, world_model=world_model,
            event_classifier=self.event_classifier,
            frequent_places=places,
            pending_shopping=pending_shopping,
        )
        bank = default_bank()

        if not clips and not bank:
            logger.info("[capsule] nothing to build for {}", date)
            return None

        await self._write_transcripts(clips, bank)

        prefix = f"capsule_{date}"
        synth_items = self._synth_items(clips, bank)
        synth_map = await self._batch_synthesize(prefix, synth_items)
        self._apply_audio_urls(clips, bank, synth_map)

        manifest = self._build_manifest(date=date, clips=clips, bank=bank)
        persisted = await push_manifest(
            session=self.session,
            backend_url=self.backend_url,
            api_key=self.api_key,
            manifest=manifest,
        )
        if persisted:
            self._publish_ready(date)
        return manifest

    # --- internals -------------------------------------------------------- #

    async def _fetch_frequent_places(self) -> list[dict]:
        """GET /frequent-places/ — returns enabled places only."""
        url = f"{self.backend_url}/frequent-places/?enabled_only=true"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with self.session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[capsule] frequent-places fetch failed: {}", exc)
        return []

    async def _fetch_pending_shopping(self) -> list[dict]:
        """GET /shopping/ — pending (not purchased) items only."""
        url = f"{self.backend_url}/shopping/?include_purchased=false"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with self.session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[capsule] shopping fetch failed: {}", exc)
        return []

    async def _write_transcripts(self, clips: list[ClipSpec], bank: list[GenericSpec]) -> None:
        for c in clips:
            c.transcript = await self.writer.write(c.transcript_seed, tone=c.tone)
        # Generic bank goes direct — no per-clip rewrite needed; PersonaRewriter
        # applied to each tag separately gives repetitive output for short lines.
        # Boot-load can tighten this later; for now seed text is shipped as-is.

    def _synth_items(
        self, clips: list[ClipSpec], bank: list[GenericSpec],
    ) -> list[dict]:
        items: list[dict] = []
        for c in clips:
            items.append({
                "clip_id": c.id,
                "text": c.transcript or c.transcript_seed,
                "tone": c.tone,
            })
        for b in bank:
            items.append({"clip_id": b.id, "text": b.text, "tone": b.tone})
        return items

    async def _batch_synthesize(self, prefix: str, items: list[dict]) -> dict[str, str]:
        """POST /api/voice/batch-synthesize → {clip_id: audio_url}."""
        if not items:
            return {}
        url = f"{self.voice_service_url}/api/voice/batch-synthesize"
        try:
            async with self.session.post(
                url, json={"prefix": prefix, "items": items}, timeout=120,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(
                        "[capsule] batch-synth failed: status={} body={}",
                        resp.status, text[:200],
                    )
                    return {}
                data = await resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[capsule] batch-synth error: {}", exc)
            return {}

        out: dict[str, str] = {}
        for r in data.get("results", []):
            if r.get("audio_url"):
                out[r["clip_id"]] = r["audio_url"]
        return out

    def _apply_audio_urls(
        self, clips: list[ClipSpec], bank: list[GenericSpec], synth_map: dict[str, str],
    ) -> None:
        for c in clips:
            c.audio_url = synth_map.get(c.id, "")
        # Generic bank has no audio_url field on the dataclass — map is used
        # when building the manifest below.

    def _build_manifest(
        self, *, date: str, clips: list[ClipSpec], bank: list[GenericSpec],
    ) -> dict:
        synth_for_bank = {b.id: b for b in bank}
        manifest_clips = [
            {
                "id": c.id,
                "trigger": _trigger_dict(c),
                "audio_url": c.audio_url or "",
                "transcript": c.transcript or c.transcript_seed,
                "priority": c.priority,
                "tone": c.tone,
                "tags": c.tags,
            }
            for c in clips
            if c.audio_url  # drop clips whose synth failed
        ]
        manifest_bank = [
            {
                "id": b.id,
                "tag": b.tag,
                "audio_url": "",  # filled via synth_map below
                "transcript": b.text,
            }
            for b in bank
        ]
        return {
            "capsule_id": date,
            "character_version": self.character_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "clips": manifest_clips,
            "generic_bank": manifest_bank,
        }

    def _publish_ready(self, date: str) -> None:
        if not self.mqtt_client:
            return
        try:
            self.mqtt_client.publish(
                "hems/voice-capsule/ready",
                json.dumps({"capsule_id": date}, ensure_ascii=False),
                qos=1,
                retain=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[capsule] MQTT ready publish failed: {}", exc)


def _trigger_dict(c: ClipSpec) -> dict:
    out: dict = {"kind": c.trigger_kind}
    if c.trigger_at_ts is not None:
        out["absolute_ts"] = c.trigger_at_ts
    if c.event_ref:
        out["event_id"] = c.event_ref
    if c.event_offset_min is not None:
        out["offset_min"] = c.event_offset_min
    if c.place_id is not None:
        # Use "place_<id>" so the phone's GeofencingClient gets a stable zone
        # string — backend `FrequentPlace.id` is the source of truth.
        out["zone"] = f"place_{c.place_id}"
        out["event"] = "enter"
    if c.cooldown_min is not None:
        out["cooldown_min"] = c.cooldown_min
    if c.place_lat is not None:
        out["lat"] = c.place_lat
    if c.place_lon is not None:
        out["lon"] = c.place_lon
    if c.place_radius_m is not None:
        out["radius_m"] = c.place_radius_m
    if c.biometric_metric is not None:
        out["metric"] = c.biometric_metric
    if c.biometric_op is not None:
        out["op"] = c.biometric_op
    if c.biometric_value is not None:
        out["value"] = c.biometric_value
    return out
