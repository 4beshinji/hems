"""
Tests for RuleEngine PC rules.
"""
import pytest
from world_model.data_classes import GPUData, DiskData, DiskPartition


class TestRuleEnginePCRules:
    """Test PC-specific rules in the rule engine."""

    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}  # reset cooldowns
        return engine

    def test_gpu_hot_generates_speak(self, world_model):
        engine = self._make_engine()
        world_model.pc_state.gpu = GPUData(temp_c=90, last_update=1.0)

        actions = engine.evaluate(world_model)
        speak_actions = [a for a in actions if a["tool"] == "speak" and "GPU" in a["args"]["message"]]
        assert len(speak_actions) == 1
        assert speak_actions[0]["args"]["tone"] == "alert"
        assert "90" in speak_actions[0]["args"]["message"]

    def test_gpu_normal_no_action(self, world_model):
        engine = self._make_engine()
        world_model.pc_state.gpu = GPUData(temp_c=70, last_update=1.0)

        actions = engine.evaluate(world_model)
        gpu_actions = [a for a in actions if "GPU" in a["args"].get("message", "")]
        assert len(gpu_actions) == 0

    def test_disk_high_generates_task(self, world_model):
        engine = self._make_engine()
        world_model.pc_state.disk = DiskData(
            partitions=[DiskPartition(mount="/", used_gb=480, total_gb=500, percent=96)],
            last_update=1.0,
        )

        actions = engine.evaluate(world_model)
        task_actions = [a for a in actions if a["tool"] == "create_task" and "ディスク" in a["args"]["title"]]
        assert len(task_actions) == 1
        assert "96" in task_actions[0]["args"]["description"]

    def test_disk_normal_no_action(self, world_model):
        engine = self._make_engine()
        world_model.pc_state.disk = DiskData(
            partitions=[DiskPartition(mount="/", used_gb=200, total_gb=500, percent=40)],
            last_update=1.0,
        )

        actions = engine.evaluate(world_model)
        disk_actions = [a for a in actions if a["tool"] == "create_task" and "ディスク" in a["args"].get("title", "")]
        assert len(disk_actions) == 0

    def test_gpu_hot_cooldown(self, world_model):
        engine = self._make_engine()
        world_model.pc_state.gpu = GPUData(temp_c=90, last_update=1.0)

        actions1 = engine.evaluate(world_model)
        actions2 = engine.evaluate(world_model)

        gpu1 = [a for a in actions1 if "GPU" in a["args"].get("message", "")]
        gpu2 = [a for a in actions2 if "GPU" in a["args"].get("message", "")]
        assert len(gpu1) == 1
        assert len(gpu2) == 0  # Cooldown active

    def test_multiple_disk_partitions(self, world_model):
        engine = self._make_engine()
        world_model.pc_state.disk = DiskData(
            partitions=[
                DiskPartition(mount="/", used_gb=480, total_gb=500, percent=96),
                DiskPartition(mount="/home", used_gb=900, total_gb=1000, percent=90),  # exactly 90 — not over
                DiskPartition(mount="/data", used_gb=950, total_gb=1000, percent=95),
            ],
            last_update=1.0,
        )

        actions = engine.evaluate(world_model)
        disk_tasks = [a for a in actions if a["tool"] == "create_task" and "ディスク" in a["args"]["title"]]
        # / (96%) and /data (95%) should trigger, /home (90%) should not
        assert len(disk_tasks) == 2
