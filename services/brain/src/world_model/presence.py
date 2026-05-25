"""WorldModel mixin extracted from the facade module."""

from . import world_model as _world_model


class PresenceMixin:
    def reconcile_presence(self) -> dict[str, dict]:
        """Run multi-source presence inference across all zones.

        Populates _world_model.OccupancyData.inferred_occupied / inference_source /
        inference_sources for every known zone. Also returns a summary
        dict keyed by zone for callers that want it.
        """
        now = _world_model.time.time()
        global_signals = self._global_presence_signals(now)
        summary: dict[str, dict] = {}

        # Any zone ever seen counts. If no zones have been created yet
        # (e.g. cold start with only biometric/PC data), treat "home"
        # as the default zone so inference still runs.
        zone_ids = list(self.zones.keys())
        if not zone_ids and (global_signals["pc_active"] or global_signals["biometric_fresh"]):
            zone_ids = ["home"]

        for zone_id in zone_ids:
            zone = self._get_zone(zone_id)
            sources: list[str] = []

            # 1. Camera — strongest
            if zone.occupancy.count > 0:
                sources.append("camera")

            # 2. HA/Zigbee/SwitchBot binary presence sensor
            if zone.occupancy.presence_state is True:
                sources.append("presence_sensor")

            # 3. Recent motion events (counter window)
            if (
                zone.occupancy.last_motion_ts > 0
                and now - zone.occupancy.last_motion_ts < self.PRESENCE_MOTION_RECENT_SEC
            ) or zone.occupancy.motion_event_count_5min > 0:
                sources.append("motion")

            # 4. Global signals (PC, biometrics) — attach only to the PC/biometric zone.
            # We don't have a reliable way to locate the user, so attribute to
            # the first zone seen (typically the primary living/work zone) or
            # to any zone if only one exists.
            is_primary = zone_id == zone_ids[0]
            if is_primary:
                if global_signals["pc_active"]:
                    sources.append("pc_activity")
                if global_signals["biometric_fresh"]:
                    sources.append("biometric")

            occupied = bool(sources)
            zone.occupancy.inferred_occupied = occupied
            zone.occupancy.inference_sources = sources
            zone.occupancy.inference_source = sources[0] if sources else "none"
            summary[zone_id] = {
                "occupied": occupied,
                "sources": list(sources),
                "camera_count": zone.occupancy.count,
                "presence_state": zone.occupancy.presence_state,
            }

        return summary

    def _global_presence_signals(self, now: float) -> dict[str, bool]:
        """Compute PC + biometric signals that don't belong to a specific zone."""
        pc = self.digital.pc_state
        pc_active = bool(
            pc.cpu.last_update > 0
            and (now - pc.cpu.last_update) < self.PRESENCE_PC_FRESH_SEC
            and pc.cpu.usage_percent >= self.PRESENCE_PC_CPU_ACTIVE
        )

        bio = self.user.biometrics
        hr_fresh = bool(
            bio.heart_rate.bpm
            and bio.heart_rate.last_update > 0
            and (now - bio.heart_rate.last_update) < self.PRESENCE_BIOMETRIC_FRESH_SEC
        )
        return {"pc_active": pc_active, "biometric_fresh": hr_fresh}

    def is_anyone_home(self) -> bool:
        """Return True if any presence source indicates occupancy in any zone.

        Use this instead of `all(z.occupancy.count == 0 ...)` to avoid
        false absences when the camera is offline but PIR/motion/PC/HR
        signals are active.
        """
        self.reconcile_presence()
        return any(z.occupancy.inferred_occupied for z in self.zones.values())

    def presence_sources(self) -> list[str]:
        """Return the union of inference sources across all zones."""
        seen: list[str] = []
        for z in self.zones.values():
            for s in z.occupancy.inference_sources:
                if s not in seen:
                    seen.append(s)
        return seen
