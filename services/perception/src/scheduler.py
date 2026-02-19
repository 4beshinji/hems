"""
Task Scheduler - 複数の監視タスクを並行実行
"""
import asyncio
import logging
from typing import Dict
from monitors.base import MonitorBase

logger = logging.getLogger(__name__)

class TaskScheduler:
    def __init__(self):
        self.monitors: Dict[str, MonitorBase] = {}
        
    def register_monitor(self, name: str, monitor: MonitorBase):
        """監視タスクを登録"""
        self.monitors[name] = monitor
        logger.info(f"Registered monitor: {name}")
        
    async def run(self):
        """全ての監視タスクを並行実行"""
        logger.info(f"Starting {len(self.monitors)} monitors")
        
        tasks = [
            asyncio.create_task(self._run_monitor(name, monitor))
            for name, monitor in self.monitors.items()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _run_monitor(self, name: str, monitor: MonitorBase):
        """個別の監視タスク実行（エラーハンドリング付き）"""
        try:
            await monitor.run()
        except Exception as e:
            logger.error(f"Monitor {name} crashed: {e}", exc_info=True)
            # 再起動ロジックを追加可能
