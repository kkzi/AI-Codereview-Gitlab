"""性能监控模块

提供关键性能指标的收集和记录功能。
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MetricRecord:
    """性能指标记录"""
    name: str
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self._metrics: List[MetricRecord] = []
        self._counters: Dict[str, int] = {}
        self._timers: Dict[str, List[float]] = {}

    def record_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """记录性能指标

        Args:
            name: 指标名称
            value: 指标值
            labels: 标签（可选）
        """
        record = MetricRecord(
            name=name,
            value=value,
            timestamp=time.time(),
            labels=labels or {}
        )
        self._metrics.append(record)

        # 保持最近 1000 条记录
        if len(self._metrics) > 1000:
            self._metrics = self._metrics[-1000:]

    def increment_counter(self, name: str, value: int = 1):
        """增加计数器

        Args:
            name: 计数器名称
            value: 增加的值（默认 1）
        """
        self._counters[name] = self._counters.get(name, 0) + value

    def record_duration(self, name: str, duration: float):
        """记录持续时间

        Args:
            name: 操作名称
            duration: 持续时间（秒）
        """
        if name not in self._timers:
            self._timers[name] = []

        self._timers[name].append(duration)

        # 保持最近 100 条记录
        if len(self._timers[name]) > 100:
            self._timers[name] = self._timers[name][-100:]

        # 记录到日志（如果超过阈值）
        if duration > 5.0:
            logger.warning(f"慢操作: {name} 耗时 {duration:.2f}s")

    @contextmanager
    def measure(self, operation: str, labels: Optional[Dict[str, str]] = None):
        """测量操作耗时的上下文管理器

        Args:
            operation: 操作名称
            labels: 标签（可选）

        Example:
            with monitor.measure("llm_api_call", {"provider": "openai"}):
                result = llm_client.chat(...)
        """
        start_time = time.time()
        success = False

        try:
            yield
            success = True
        finally:
            duration = time.time() - start_time
            self.record_duration(operation, duration)
            self.record_metric(
                f"{operation}_duration",
                duration,
                labels={**(labels or {}), "success": str(success)}
            )

            # 更新计数器
            counter_name = f"{operation}_total"
            self.increment_counter(counter_name)

            if success:
                self.increment_counter(f"{operation}_success")
            else:
                self.increment_counter(f"{operation}_failure")

    def get_stats(self, name: str) -> Dict[str, float]:
        """获取操作的统计信息

        Args:
            name: 操作名称

        Returns:
            包含 min, max, avg, p50, p95, p99 的字典
        """
        if name not in self._timers or not self._timers[name]:
            return {}

        durations = sorted(self._timers[name])
        count = len(durations)

        return {
            "count": count,
            "min": durations[0],
            "max": durations[-1],
            "avg": sum(durations) / count,
            "p50": durations[int(count * 0.5)],
            "p95": durations[int(count * 0.95)] if count > 1 else durations[0],
            "p99": durations[int(count * 0.99)] if count > 1 else durations[0],
        }

    def get_counter(self, name: str) -> int:
        """获取计数器值

        Args:
            name: 计数器名称

        Returns:
            计数器值
        """
        return self._counters.get(name, 0)

    def get_success_rate(self, operation: str) -> float:
        """获取操作成功率

        Args:
            operation: 操作名称

        Returns:
            成功率（0.0-1.0）
        """
        total = self.get_counter(f"{operation}_total")
        if total == 0:
            return 0.0

        success = self.get_counter(f"{operation}_success")
        return success / total

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """获取所有操作的统计信息

        Returns:
            操作名称到统计信息的映射
        """
        return {name: self.get_stats(name) for name in self._timers.keys()}

    def get_all_counters(self) -> Dict[str, int]:
        """获取所有计数器

        Returns:
            计数器名称到值的映射
        """
        return self._counters.copy()

    def log_summary(self):
        """输出性能监控摘要到日志"""
        logger.info("=== 性能监控摘要 ===")

        # 输出计数器
        if self._counters:
            logger.info("计数器:")
            for name, value in sorted(self._counters.items()):
                logger.info(f"  {name}: {value}")

        # 输出统计信息
        if self._timers:
            logger.info("操作统计:")
            for name in sorted(self._timers.keys()):
                stats = self.get_stats(name)
                if stats:
                    logger.info(
                        f"  {name}: "
                        f"count={stats['count']}, "
                        f"avg={stats['avg']:.3f}s, "
                        f"p95={stats['p95']:.3f}s, "
                        f"p99={stats['p99']:.3f}s"
                    )

        # 输出成功率
        operations = set()
        for counter_name in self._counters.keys():
            if counter_name.endswith("_total"):
                operations.add(counter_name[:-6])

        if operations:
            logger.info("成功率:")
            for operation in sorted(operations):
                rate = self.get_success_rate(operation)
                logger.info(f"  {operation}: {rate:.1%}")


# 全局监控实例
_monitor = PerformanceMonitor()


def get_monitor() -> PerformanceMonitor:
    """获取全局性能监控实例

    Returns:
        性能监控实例
    """
    return _monitor
