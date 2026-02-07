"""单元测试：性能监控"""
import time
import unittest

from app.core.performance import PerformanceMonitor


class TestPerformanceMonitor(unittest.TestCase):
    def setUp(self):
        """测试前准备"""
        self.monitor = PerformanceMonitor()

    def test_record_metric(self):
        """测试记录性能指标"""
        self.monitor.record_metric("test_metric", 1.5, {"label": "value"})

        # 验证指标已记录
        self.assertEqual(len(self.monitor._metrics), 1)
        self.assertEqual(self.monitor._metrics[0].name, "test_metric")
        self.assertEqual(self.monitor._metrics[0].value, 1.5)
        self.assertEqual(self.monitor._metrics[0].labels["label"], "value")

    def test_increment_counter(self):
        """测试增加计数器"""
        self.monitor.increment_counter("test_counter", 5)
        self.assertEqual(self.monitor.get_counter("test_counter"), 5)

        self.monitor.increment_counter("test_counter", 3)
        self.assertEqual(self.monitor.get_counter("test_counter"), 8)

    def test_record_duration(self):
        """测试记录持续时间"""
        self.monitor.record_duration("test_operation", 1.5)
        self.monitor.record_duration("test_operation", 2.0)
        self.monitor.record_duration("test_operation", 1.0)

        stats = self.monitor.get_stats("test_operation")
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["min"], 1.0)
        self.assertEqual(stats["max"], 2.0)
        self.assertAlmostEqual(stats["avg"], 1.5, places=2)

    def test_measure_context_manager_success(self):
        """测试测量上下文管理器（成功）"""
        with self.monitor.measure("test_op", {"env": "test"}):
            time.sleep(0.01)

        # 验证计数器
        self.assertEqual(self.monitor.get_counter("test_op_total"), 1)
        self.assertEqual(self.monitor.get_counter("test_op_success"), 1)
        self.assertEqual(self.monitor.get_counter("test_op_failure"), 0)

        # 验证持续时间
        stats = self.monitor.get_stats("test_op")
        self.assertGreater(stats["avg"], 0.01)

    def test_measure_context_manager_failure(self):
        """测试测量上下文管理器（失败）"""
        try:
            with self.monitor.measure("test_op_fail"):
                raise ValueError("Test error")
        except ValueError:
            pass

        # 验证计数器
        self.assertEqual(self.monitor.get_counter("test_op_fail_total"), 1)
        self.assertEqual(self.monitor.get_counter("test_op_fail_success"), 0)
        self.assertEqual(self.monitor.get_counter("test_op_fail_failure"), 1)

    def test_get_success_rate(self):
        """测试获取成功率"""
        # 模拟 3 次成功，1 次失败
        self.monitor.increment_counter("operation_total", 4)
        self.monitor.increment_counter("operation_success", 3)

        rate = self.monitor.get_success_rate("operation")
        self.assertEqual(rate, 0.75)

    def test_get_success_rate_no_data(self):
        """测试获取成功率（无数据）"""
        rate = self.monitor.get_success_rate("nonexistent")
        self.assertEqual(rate, 0.0)

    def test_get_stats_percentiles(self):
        """测试统计信息的百分位数"""
        # 添加 100 个数据点
        for i in range(100):
            self.monitor.record_duration("percentile_test", i / 10.0)

        stats = self.monitor.get_stats("percentile_test")
        self.assertEqual(stats["count"], 100)
        self.assertAlmostEqual(stats["p50"], 5.0, delta=0.5)
        self.assertAlmostEqual(stats["p95"], 9.5, delta=0.5)
        self.assertAlmostEqual(stats["p99"], 9.9, delta=0.5)

    def test_metrics_limit(self):
        """测试指标记录数量限制"""
        # 添加超过 1000 条记录
        for i in range(1500):
            self.monitor.record_metric(f"metric_{i}", i)

        # 验证只保留最近 1000 条
        self.assertEqual(len(self.monitor._metrics), 1000)

    def test_timers_limit(self):
        """测试计时器记录数量限制"""
        # 添加超过 100 条记录
        for i in range(150):
            self.monitor.record_duration("timer_test", i)

        # 验证只保留最近 100 条
        self.assertEqual(len(self.monitor._timers["timer_test"]), 100)

    def test_get_all_stats(self):
        """测试获取所有统计信息"""
        self.monitor.record_duration("op1", 1.0)
        self.monitor.record_duration("op2", 2.0)

        all_stats = self.monitor.get_all_stats()
        self.assertIn("op1", all_stats)
        self.assertIn("op2", all_stats)
        self.assertEqual(all_stats["op1"]["count"], 1)
        self.assertEqual(all_stats["op2"]["count"], 1)

    def test_get_all_counters(self):
        """测试获取所有计数器"""
        self.monitor.increment_counter("counter1", 10)
        self.monitor.increment_counter("counter2", 20)

        all_counters = self.monitor.get_all_counters()
        self.assertEqual(all_counters["counter1"], 10)
        self.assertEqual(all_counters["counter2"], 20)


if __name__ == "__main__":
    unittest.main()
