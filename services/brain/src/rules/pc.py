"""PC / VLM / screen-time RuleEngine rules.

Extracted (W2.4) from the loop-external inline blocks of ``RuleEngine.evaluate``.
These blocks are *interleaved* with existing mixin calls in the source:

    P1,P2 (GPU/disk)  -> M1 device_health -> M2 service_vip
    -> V1 (VLM swap)  -> P3 (heavy process)
    -> M3 GAS -> M4 home/zigbee -> Z13 (screen time) -> M5..M7

To preserve the exact emission order, each block is its own ``_evaluate_*``
method and the orchestrator (``RuleEngine.evaluate``) calls them at the same
position they occupied inline — NOT bundled into a single PC method (which would
move P3 ahead of the device_health/service_vip/VLM mixin calls).
"""


class PCRulesMixin:
    def _evaluate_pc_basic_rules(self, world_model, now: float) -> list[dict]:
        """P1 GPU temperature + P2 disk usage (contiguous source block)."""
        actions: list[dict] = []
        pc = world_model.pc_state

        if pc.gpu.temp_c > self.thresholds.pc_gpu_temp_high and self._check_cooldown("pc_gpu_hot", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"GPU温度が{pc.gpu.temp_c:.0f}度です。負荷を下げてください。",
                        "zone": "pc",
                        "tone": "alert",
                    },
                }
            )

        if pc.disk.partitions:
            for p in pc.disk.partitions:
                if p.percent > self.thresholds.pc_disk_high and self._check_cooldown(f"pc_disk_{p.mount}", now):
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"ディスク容量不足: {p.mount}",
                                "description": f"{p.mount}の使用率が{p.percent:.0f}%です。不要ファイルを削除してください。",
                                "urgency": 2,
                                "zone": "pc",
                                "task_type": ["maintenance"],
                            },
                        }
                    )
        return actions

    def _evaluate_vlm_swap(self, world_model, now: float) -> list[dict]:
        """V1 VLM swap stuck rule (B-3)."""
        actions: list[dict] = []

        if getattr(world_model, "vlm_model_swap_active", False):
            stats = getattr(world_model, "vlm_swap_stats", {})
            start = stats.get("last_swap_start_ts", 0)
            if start > 0 and (now - start) > 60 and self._check_cooldown_custom("vlm_swap_stuck", now, 1800):
                duration = int(now - start)
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": "VLM切替が長時間スタック",
                            "description": f"VLMモデル切替が{duration}秒継続しています。perception コンテナのログを確認してください。",
                            "urgency": 2,
                            "zone": "system",
                            "task_type": ["maintenance"],
                        },
                    }
                )
        return actions

    def _evaluate_heavy_processes(self, world_model, now: float) -> list[dict]:
        """P3 heavy-process rules (B-1): CPU sustained or single-process memory.

        Owns the ``_heavy_proc_since`` tracker (set/pop) and the post-loop GC of
        stale process names.  ``seen_names`` stays local to this method.
        """
        actions: list[dict] = []
        pc = world_model.pc_state

        # CPU sustained > 90% for 5min, or single process > 4GB memory
        seen_names: set[str] = set()
        if pc.top_processes:
            for proc in pc.top_processes:
                if not proc.name:
                    continue
                seen_names.add(proc.name)
                # Skip dev-environment noise (Chrome, Slack, VS Code, etc.)
                pname_lower = proc.name.lower()
                if any(ex in pname_lower for ex in self.thresholds.pc_proc_heavy_exclude):
                    continue
                # CPU sustained
                if proc.cpu_percent >= self.thresholds.pc_proc_cpu_high:
                    start = self._heavy_proc_since.setdefault(proc.name, now)
                    if now - start >= self.thresholds.pc_proc_cpu_sustain_s and self._check_cooldown_custom(
                        f"pc_proc_cpu_{proc.name}", now, self.thresholds.pc_proc_cooldown_s
                    ):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"{proc.name} がCPUを{proc.cpu_percent:.0f}%占有しています。閉じても大丈夫ですか？",
                                    "zone": "pc",
                                    "tone": "alert",
                                },
                            }
                        )
                else:
                    self._heavy_proc_since.pop(proc.name, None)
                # Memory single-process
                mem_gb = proc.mem_mb / 1024.0
                if mem_gb >= self.thresholds.pc_proc_mem_high_gb and self._check_cooldown_custom(
                    f"pc_proc_mem_{proc.name}", now, self.thresholds.pc_proc_cooldown_s
                ):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{proc.name} が{mem_gb:.1f}GBメモリを使っています。再起動を検討してください。",
                                "zone": "pc",
                                "tone": "caring",
                            },
                        }
                    )
        # GC: process names that disappeared from the top list, including
        # when the top-process payload is now empty.
        for stale in [n for n in self._heavy_proc_since if n not in seen_names]:
            self._heavy_proc_since.pop(stale, None)
        return actions

    def _evaluate_screen_time(self, world_model, now: float) -> list[dict]:
        """Z13 screen-time rule."""
        actions: list[dict] = []
        st = world_model.user.screen_time

        if st.total_minutes >= self.thresholds.screen_time_alert_minutes and self._check_cooldown(
            "screen_time_alert", now
        ):
            hours = st.total_minutes // 60
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"画面を{hours}時間以上見ています。目を休めましょう。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )
        return actions
