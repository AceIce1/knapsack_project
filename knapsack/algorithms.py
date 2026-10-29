"""实现四种背包算法；只有完整完成搜索或递推的精确算法才能标记为最优。"""

import math
import time
from fractions import Fraction

from .models import Instance, Result, validate_result


ALGORITHMS = {
    "greedy": "价值重量比贪心",
    "dynamic_programming": "动态规划",
    "branch_and_bound": "分支限界",
    "brute_force": "穷举搜索",
}
STATUS_LABELS = {
    "optimal": "已证明最优",
    "heuristic": "启发式可行解",
    "timeout": "超时可行解",
    "cancelled": "已取消",
    "skipped": "资源限制跳过",
}


class _Budget:
    """在各算法之间统一管理计时与取消信号，不负责强制终止线程。"""

    def __init__(self, seconds, cancel):
        """使用单调的高精度时钟记录起点和截止时刻。"""
        self.start = time.perf_counter_ns()
        self.deadline = self.start + seconds * 1_000_000_000
        self.cancel = cancel

    def stopped(self):
        """返回取消或超时状态；空字符串表示仍可继续计算。"""
        if self.cancel is not None and self.cancel.is_set():
            return "cancelled"
        if time.perf_counter_ns() >= self.deadline:
            return "timeout"
        return ""


def _density_order(instance):
    """按价值重量比降序排列，同密度时保持原始下标顺序。"""
    # 使用精确分数比较，避免大整数先转为浮点数后丢失精度。
    return sorted(
        range(len(instance.items)),
        key=lambda i: (-Fraction(instance.items[i].value, instance.items[i].weight), i),
    )


def _greedy(instance, order=None):
    """顺序检查排序后的物品，能装下就选取；只保证可行，不保证最优。"""
    remaining = instance.capacity
    chosen = []
    for i in order if order is not None else _density_order(instance):
        item = instance.items[i]
        if item.weight <= remaining and item.value > 0:
            chosen.append(i)
            remaining -= item.weight
    return tuple(sorted(chosen))


def _value(instance, indices):
    """根据物品下标重新累加总价值。"""
    return sum(instance.items[i].value for i in indices)


def _decode_mask(mask, order):
    """将搜索节点的二进制选择掩码还原为原始物品下标。"""
    return tuple(sorted(order[i] for i in range(len(order)) if mask & (1 << i)))


def _search(instance, budget, bounded):
    """共用选与不选的搜索框架，bounded 决定是否启用价值上界剪枝。"""
    order = _density_order(instance) if bounded else list(range(len(instance.items)))
    chosen = _greedy(instance)
    # 用一个现成可行解初始化下界，超时时也能返回合法选择。
    best_value = _value(instance, chosen)
    operations = 0
    stack = [(0, 0, 0, 0)]
    # 节点依次保存：已决策层数、当前重量、当前价值、选择掩码。
    items = instance.items

    def upper_bound(level, weight, value):
        """允许剩余物品被切分，计算不低于真实整数最优值的上界。"""
        remaining = instance.capacity - weight
        bound = value
        for k in range(level, len(order)):
            item = items[order[k]]
            if item.weight <= remaining:
                remaining -= item.weight
                bound += item.value
            else:
                # 整数价值的最优解不超过分数背包上界的向下取整值。
                bound += remaining * item.value // item.weight
                break
        return bound

    while stack:
        # 定期检查预算，减少每个节点都读取时钟带来的额外开销。
        if operations % 256 == 0 and (status := budget.stopped()):
            return chosen, status, operations, ""
        level, weight, value, mask = stack.pop()
        operations += 1
        if value > best_value:
            best_value = value
            chosen = _decode_mask(mask, order)
        if level == len(order):
            continue
        if bounded and upper_bound(level, weight, value) <= best_value:
            # 这个分支的最好可能结果也不能改善下界，因此可以整体舍弃。
            continue
        item = items[order[level]]
        stack.append((level + 1, weight, value, mask))
        # 栈后进先出：先压入不选分支，再压入选取分支，使选取分支先展开。
        if weight + item.weight <= instance.capacity:
            stack.append((level + 1, weight + item.weight, value + item.value, mask | (1 << level)))
    return chosen, "optimal", operations, ""


def _dynamic_programming(instance, budget, max_cells):
    """容量倒序递推并保存决策，完整结束后回溯所选物品。"""
    n = len(instance.items)
    capacity = min(instance.capacity, sum(item.weight for item in instance.items))
    # 容量大于所有物品总重量时无需扩大状态表，等价地使用有效容量。
    if n * (capacity + 1) > max_cells:
        return _greedy(instance), "skipped", 0, f"n*(C+1) exceeds {max_cells:,} cells; greedy fallback."
    values = [0] * (capacity + 1)
    decisions = []
    # 价值数组只占 O(C)，但为回溯保存的逐行决策总共占 O(nC) 空间。
    operations = 0

    def reconstruct():
        """从最后一行向前检查选取标记，还原一个与当前状态一致的可行解。"""
        remaining = capacity
        indices = []
        for i in range(len(decisions) - 1, -1, -1):
            if decisions[i][remaining]:
                indices.append(i)
                remaining -= instance.items[i].weight
        return tuple(reversed(indices))

    for item in instance.items:
        if status := budget.stopped():
            return reconstruct(), status, operations, ""
        take = bytearray(capacity + 1)
        decisions.append(take)
        # 必须倒序遍历：读取较小容量时，它仍属于上一轮，因而不会重复选当前物品。
        for c in range(capacity, item.weight - 1, -1):
            if operations % 1024 == 0 and (status := budget.stopped()):
                return reconstruct(), status, operations, ""
            candidate = values[c - item.weight] + item.value
            if candidate > values[c]:
                # 仅在严格改善价值时更新，同价值方案保留原先的选择。
                values[c] = candidate
                take[c] = 1
            operations += 1
    return reconstruct(), "optimal", operations, ""


def solve(
    instance: Instance,
    algorithm: str,
    time_limit: float = 5.0,
    cancel=None,
    max_dp_cells: int = 20_000_000,
) -> Result:
    """按照统一接口求解，并独立校验返回结果。

    instance 为已校验的问题实例，algorithm 为算法标识。
    time_limit 是每个算法的合作式秒数预算，不是硬实时截止保证。
    cancel 可传入线程事件，使长时间搜索能够响应取消。
    max_dp_cells 限制动态规划决策表的规模，超限时明确跳过并附上贪心解。
    耗时包括排序、算法和方案回溯，不包括文件读写和最后的独立校验。
    不同算法可能返回不同的等价值最优物品组合。
    """
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    if isinstance(time_limit, bool) or not isinstance(time_limit, (int, float)):
        raise ValueError("Time limit must be a finite positive number.")
    if not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError("Time limit must be a finite positive number.")
    if type(max_dp_cells) is not int or max_dp_cells <= 0:
        raise ValueError("DP cell limit must be a positive integer.")
    budget = _Budget(time_limit, cancel)
    if status := budget.stopped():
        chosen, operations, note = (), 0, ""
    elif algorithm == "greedy":
        chosen, operations, note = _greedy(instance), len(instance.items), ""
        status = budget.stopped() or "heuristic"
    elif algorithm == "dynamic_programming":
        chosen, status, operations, note = _dynamic_programming(instance, budget, max_dp_cells)
    else:
        chosen, status, operations, note = _search(instance, budget, algorithm == "branch_and_bound")
    result = Result(
        algorithm,
        tuple(chosen),
        sum(instance.items[i].weight for i in chosen),
        _value(instance, chosen),
        (time.perf_counter_ns() - budget.start) / 1_000_000,
        status,
        operations,
        note,
    )
    validate_result(instance, result)
    return result
