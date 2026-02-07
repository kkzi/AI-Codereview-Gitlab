"""性能监控 API 路由"""
from __future__ import annotations

from flask import Blueprint, jsonify

from app.api.auth import login_required
from app.core.performance import get_monitor


metrics_bp = Blueprint("metrics", __name__)


@metrics_bp.route("/metrics/stats")
@login_required
def get_stats():
    """获取所有操作的统计信息"""
    monitor = get_monitor()
    return jsonify({
        "stats": monitor.get_all_stats(),
        "counters": monitor.get_all_counters(),
    })


@metrics_bp.route("/metrics/summary")
@login_required
def get_summary():
    """获取性能监控摘要"""
    monitor = get_monitor()

    # 计算成功率
    operations = set()
    for counter_name in monitor.get_all_counters().keys():
        if counter_name.endswith("_total"):
            operations.add(counter_name[:-6])

    success_rates = {}
    for operation in operations:
        rate = monitor.get_success_rate(operation)
        if rate > 0:
            success_rates[operation] = rate

    return jsonify({
        "stats": monitor.get_all_stats(),
        "counters": monitor.get_all_counters(),
        "success_rates": success_rates,
    })
