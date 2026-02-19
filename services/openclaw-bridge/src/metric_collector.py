"""
Periodic PC metric collector via OpenClaw system.run().
Parses CPU, memory, GPU, disk, temperature, and process data.
"""
import asyncio
import json
import time
from loguru import logger


class MetricCollector:
    """Collects PC metrics by running commands through OpenClaw."""

    def __init__(self, openclaw_client, mqtt_publisher, metrics_interval: int = 10,
                 process_interval: int = 30):
        self.oc = openclaw_client
        self.mqtt = mqtt_publisher
        self.metrics_interval = metrics_interval
        self.process_interval = process_interval
        self.last_metrics: dict = {}
        self.last_processes: list[dict] = []

        # Threshold state for edge-triggered events
        self._prev_cpu_high = False
        self._prev_mem_high = False
        self._prev_gpu_hot = False
        self._prev_disk_low: dict[str, bool] = {}

    async def run_metrics_loop(self):
        """Collect system metrics every metrics_interval seconds."""
        while True:
            try:
                if self.oc.connected:
                    await self._collect_metrics()
            except Exception as e:
                logger.debug(f"Metrics collection error: {e}")
            await asyncio.sleep(self.metrics_interval)

    async def run_process_loop(self):
        """Collect top processes every process_interval seconds."""
        while True:
            try:
                if self.oc.connected:
                    await self._collect_processes()
            except Exception as e:
                logger.debug(f"Process collection error: {e}")
            await asyncio.sleep(self.process_interval)

    async def _collect_metrics(self):
        """Run metric collection commands and publish to MQTT."""
        cpu = await self._collect_cpu()
        memory = await self._collect_memory()
        gpu = await self._collect_gpu()
        disk = await self._collect_disk()
        temps = await self._collect_temperatures()

        self.last_metrics = {
            "cpu": cpu, "memory": memory, "gpu": gpu,
            "disk": disk, "temperature": temps,
            "timestamp": time.time(),
        }

        # Publish each metric category
        if cpu:
            self.mqtt.publish("hems/pc/metrics/cpu", cpu)
        if memory:
            self.mqtt.publish("hems/pc/metrics/memory", memory)
        if gpu:
            self.mqtt.publish("hems/pc/metrics/gpu", gpu)
        if disk:
            self.mqtt.publish("hems/pc/metrics/disk", disk)
        if temps:
            self.mqtt.publish("hems/pc/metrics/temperature", temps)

        # Check thresholds for event publishing
        self._check_events(cpu, memory, gpu, disk)

    async def _collect_cpu(self) -> dict:
        try:
            result = await self.oc.system_run(
                "python3 -c \""
                "import json, os; "
                "loads = os.getloadavg(); "
                "cpus = os.cpu_count() or 1; "
                "print(json.dumps({'usage_percent': round(loads[0] / cpus * 100, 1), "
                "'core_count': cpus, 'load_1m': loads[0]}))\"",
                timeout=10,
            )
            output = result.get("stdout", "").strip()
            if output:
                return json.loads(output)
        except Exception as e:
            logger.debug(f"CPU collection failed: {e}")
        return {}

    async def _collect_memory(self) -> dict:
        try:
            result = await self.oc.system_run(
                "python3 -c \""
                "import json; "
                "m = {}; "
                "with open('/proc/meminfo') as f: "
                "    for line in f: "
                "        parts = line.split(); "
                "        if parts[0] in ('MemTotal:', 'MemAvailable:'):"
                "            m[parts[0][:-1]] = int(parts[1]) * 1024; "
                "total = m.get('MemTotal', 0); "
                "avail = m.get('MemAvailable', 0); "
                "used = total - avail; "
                "print(json.dumps({'used_gb': round(used/1073741824, 2), "
                "'total_gb': round(total/1073741824, 2), "
                "'percent': round(used/total*100, 1) if total else 0}))\"",
                timeout=10,
            )
            output = result.get("stdout", "").strip()
            if output:
                return json.loads(output)
        except Exception as e:
            logger.debug(f"Memory collection failed: {e}")
        return {}

    async def _collect_gpu(self) -> dict:
        try:
            # Try nvidia-smi first
            result = await self.oc.system_run(
                "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu "
                "--format=csv,noheader,nounits 2>/dev/null || "
                "rocm-smi --showuse --showmeminfo vram --showtemp --csv 2>/dev/null || echo ''",
                timeout=10,
            )
            output = result.get("stdout", "").strip()
            if not output:
                return {}

            # Parse nvidia-smi output (format: "util, mem_used, mem_total, temp")
            if "," in output and not output.startswith("device"):
                parts = [p.strip() for p in output.split("\n")[0].split(",")]
                if len(parts) >= 4:
                    return {
                        "usage_percent": float(parts[0]),
                        "vram_used_gb": round(float(parts[1]) / 1024, 2),
                        "vram_total_gb": round(float(parts[2]) / 1024, 2),
                        "temp_c": float(parts[3]),
                    }
        except Exception as e:
            logger.debug(f"GPU collection failed: {e}")
        return {}

    async def _collect_disk(self) -> dict:
        try:
            result = await self.oc.system_run(
                "df -B1 --output=target,used,size,pcent -x tmpfs -x devtmpfs -x squashfs 2>/dev/null | tail -n +2",
                timeout=10,
            )
            output = result.get("stdout", "").strip()
            if not output:
                return {}

            partitions = []
            for line in output.split("\n"):
                parts = line.split()
                if len(parts) >= 4:
                    partitions.append({
                        "mount": parts[0],
                        "used_gb": round(int(parts[1]) / 1073741824, 2),
                        "total_gb": round(int(parts[2]) / 1073741824, 2),
                        "percent": float(parts[3].replace("%", "")),
                    })
            return {"partitions": partitions}
        except Exception as e:
            logger.debug(f"Disk collection failed: {e}")
        return {}

    async def _collect_temperatures(self) -> dict:
        try:
            result = await self.oc.system_run(
                "sensors -j 2>/dev/null || echo '{}'",
                timeout=10,
            )
            output = result.get("stdout", "").strip()
            if not output or output == "{}":
                return {}

            data = json.loads(output)
            temps = {}
            for chip, readings in data.items():
                if not isinstance(readings, dict):
                    continue
                for label, values in readings.items():
                    if not isinstance(values, dict):
                        continue
                    for key, val in values.items():
                        if "input" in key and isinstance(val, (int, float)):
                            if "cpu" in chip.lower() or "cpu" in label.lower() or "tctl" in label.lower():
                                temps["cpu_temp_c"] = val
                            elif "gpu" in chip.lower() or "gpu" in label.lower() or "edge" in label.lower():
                                temps["gpu_temp_c"] = val
            return temps
        except Exception as e:
            logger.debug(f"Temperature collection failed: {e}")
        return {}

    async def _collect_processes(self):
        """Collect top processes by CPU usage."""
        try:
            result = await self.oc.system_run(
                "ps aux --sort=-%cpu | head -16 | tail -15 | "
                "awk '{printf \"%s %s %.1f %.1f\\n\", $2, $11, $3, $6/1024}'",
                timeout=10,
            )
            output = result.get("stdout", "").strip()
            if not output:
                return

            processes = []
            for line in output.split("\n"):
                parts = line.split()
                if len(parts) >= 4:
                    processes.append({
                        "pid": int(parts[0]),
                        "name": parts[1].split("/")[-1],
                        "cpu_percent": float(parts[2]),
                        "mem_mb": round(float(parts[3]), 1),
                    })

            self.last_processes = processes
            self.mqtt.publish("hems/pc/processes/top", {"processes": processes})
        except Exception as e:
            logger.debug(f"Process collection failed: {e}")

    def _check_events(self, cpu: dict, memory: dict, gpu: dict, disk: dict):
        """Publish threshold events (edge-triggered)."""
        # CPU > 90%
        cpu_high = cpu.get("usage_percent", 0) > 90
        if cpu_high and not self._prev_cpu_high:
            self.mqtt.publish("hems/pc/events/cpu_high", cpu)
        self._prev_cpu_high = cpu_high

        # Memory > 90%
        mem_high = memory.get("percent", 0) > 90
        if mem_high and not self._prev_mem_high:
            self.mqtt.publish("hems/pc/events/memory_high", memory)
        self._prev_mem_high = mem_high

        # GPU temp > 85C
        gpu_hot = gpu.get("temp_c", 0) > 85
        if gpu_hot and not self._prev_gpu_hot:
            self.mqtt.publish("hems/pc/events/gpu_hot", gpu)
        self._prev_gpu_hot = gpu_hot

        # Disk > 90% (per partition)
        for partition in disk.get("partitions", []):
            mount = partition.get("mount", "")
            high = partition.get("percent", 0) > 90
            was_high = self._prev_disk_low.get(mount, False)
            if high and not was_high:
                self.mqtt.publish("hems/pc/events/disk_low", partition)
            self._prev_disk_low[mount] = high

    def get_status(self) -> dict:
        """Return cached PC status for REST API."""
        return {
            **self.last_metrics,
            "top_processes": self.last_processes,
        }
