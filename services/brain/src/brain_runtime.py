import asyncio
import time

from loguru import logger

from brain_constants import EVENT_BATCH_DELAY, summarize_action
from low_power_mode import NORMAL_HEARTBEAT_INTERVAL


class BrainRuntimeMixin:
    async def _run_cognitive_loop(self) -> None:
        last_cycle = 0.0
        while True:
            event_triggered = False
            try:
                cycle_timeout = self.power_mode_manager.cycle_interval
                await asyncio.wait_for(self._cycle_triggered.wait(), timeout=cycle_timeout)
                self._cycle_triggered.clear()
                await asyncio.sleep(EVENT_BATCH_DELAY)
                event_triggered = True
            except TimeoutError:
                pass

            # Heartbeat gate: in NORMAL mode an idle poll (no new MQTT events)
            # skips the LLM cycle until the proactive-thinking floor is due.
            if (
                not self.power_mode_manager.is_low_power
                and not event_triggered
                and (time.time() - last_cycle) < NORMAL_HEARTBEAT_INTERVAL
            ):
                continue

            min_interval = self.power_mode_manager.min_cycle_interval
            if time.time() - last_cycle < min_interval:
                await asyncio.sleep(min_interval - (time.time() - last_cycle))

            try:
                await self.cognitive_cycle()
                last_cycle = time.time()
                self._schedule_save_counter += 1
                if self._schedule_save_counter >= 10:
                    self._save_schedule_state()
                    self._schedule_save_counter = 0
            except Exception as e:
                logger.error(f"Cognitive cycle error: {e}")

            await self._run_ambient_speech_once()
            await self._run_event_automation_once()
            await self._maybe_daily_maintenance()

    async def _run_ambient_speech_once(self) -> None:
        try:
            if not self.ambient_speaker or not self.ambient_speaker.should_speak():
                return
            action = await self.ambient_speaker.generate()
            if action and self.tool_executor:
                result = await self.tool_executor.execute(action["tool"], action["args"])
                if result.get("success"):
                    self.ambient_speaker.record_speak(action["args"].get("message", ""))
                    logger.info(f"Ambient speak: {action['args'].get('message', '')[:40]}")
                self._action_history.append(
                    {
                        "time": time.time(),
                        "tool": action["tool"],
                        "summary": summarize_action(action["tool"], action["args"]),
                        "success": result.get("success", True),
                    }
                )
        except Exception as e:
            logger.warning(f"Ambient speech error: {e}")

    async def _run_event_automation_once(self) -> None:
        try:
            if self.event_automation:
                await self.event_automation.check_scheduled()
        except Exception as e:
            logger.warning(f"Event automation error: {e}")
