"""检查四种算法的解、边界条件、取消行为和输入校验。"""

import itertools
import random
import threading
import unittest

from knapsack.algorithms import ALGORITHMS, solve
from knapsack.models import Instance, Item, validate_result


def make_instance(pairs, capacity):
    """将测试中的重量价值二元组转换成统一的问题实例。"""
    return Instance(tuple(Item(str(i + 1), w, v) for i, (w, v) in enumerate(pairs)), capacity)


def independent_optimum(instance):
    """用独立的笛卡尔积枚举建立小规模最优值基准，不复用被测搜索代码。"""
    best = 0
    for bits in itertools.product((0, 1), repeat=len(instance.items)):
        weight = sum(item.weight * bit for item, bit in zip(instance.items, bits))
        value = sum(item.value * bit for item, bit in zip(instance.items, bits))
        if weight <= instance.capacity:
            best = max(best, value)
    return best


class AlgorithmTests(unittest.TestCase):
    """使用已知答案和100组随机实例，核对精确算法并检查贪心解的可行性。"""
    def test_classic_example(self):
        instance = make_instance([(10, 60), (20, 100), (30, 120)], 50)
        for algorithm in ("brute_force", "dynamic_programming", "branch_and_bound"):
            with self.subTest(algorithm=algorithm):
                result = solve(instance, algorithm)
                self.assertEqual(result.total_value, 220)
                self.assertEqual(result.status, "optimal")
                validate_result(instance, result)

    def test_greedy_is_not_an_exact_algorithm(self):
        instance = make_instance([(10, 60), (20, 100), (30, 120)], 50)
        result = solve(instance, "greedy")
        self.assertEqual(result.total_value, 160)
        self.assertEqual(result.status, "heuristic")

    def test_random_instances_against_independent_enumeration(self):
        """同一批随机输入同时交给独立枚举和各算法，避免只检查演示实例。"""
        rng = random.Random(20261029)
        for case in range(100):
            n = rng.randrange(0, 11)
            instance = make_instance(
                [(rng.randint(1, 20), rng.randint(0, 40)) for _ in range(n)],
                rng.randrange(0, 65),
            )
            optimum = independent_optimum(instance)
            for algorithm in ALGORITHMS:
                with self.subTest(case=case, algorithm=algorithm):
                    result = solve(instance, algorithm)
                    validate_result(instance, result)
                    if algorithm != "greedy":
                        self.assertEqual(result.status, "optimal")
                        self.assertEqual(result.total_value, optimum)
                    else:
                        self.assertLessEqual(result.total_value, optimum)

    def test_empty_instance(self):
        for algorithm in ALGORITHMS:
            result = solve(make_instance([], 10), algorithm)
            self.assertEqual(result.total_value, 0)
            self.assertEqual(result.selected_indices, ())

    def test_huge_capacity_with_few_items_does_not_allocate_huge_table(self):
        instance = make_instance([(2, 3), (3, 5)], 10**12)
        result = solve(instance, "dynamic_programming")
        self.assertEqual(result.total_value, 8)
        self.assertEqual(result.status, "optimal")

    def test_zero_capacity(self):
        for algorithm in ALGORITHMS:
            result = solve(make_instance([(2, 3)], 0), algorithm)
            self.assertEqual(result.total_weight, 0)
            validate_result(make_instance([(2, 3)], 0), result)

    def test_all_items_overweight(self):
        for algorithm in ALGORITHMS:
            self.assertEqual(solve(make_instance([(10, 20), (11, 90)], 3), algorithm).total_value, 0)

    def test_each_item_can_be_used_only_once(self):
        for algorithm in ALGORITHMS:
            self.assertEqual(solve(make_instance([(2, 3)], 8), algorithm).total_value, 3)

    def test_duplicate_items_are_distinct_objects(self):
        for algorithm in ALGORITHMS:
            result = solve(make_instance([(2, 5), (2, 5), (2, 5)], 4), algorithm)
            self.assertEqual(result.total_value, 10)
            self.assertEqual(len(result.selected_indices), 2)

    def test_large_integer_values_do_not_use_float_bounds(self):
        big = 10**22
        instance = make_instance([(3, big), (4, big + 1), (5, big + 2)], 9)
        for algorithm in ("brute_force", "dynamic_programming", "branch_and_bound"):
            self.assertEqual(solve(instance, algorithm).total_value, 2 * big + 3)

    def test_cancelled_results_are_feasible_not_optimal(self):
        event = threading.Event()
        event.set()
        instance = make_instance([(2, 3), (3, 5)], 4)
        for algorithm in ALGORITHMS:
            result = solve(instance, algorithm, cancel=event)
            self.assertEqual(result.status, "cancelled")
            validate_result(instance, result)

    def test_dp_resource_guard_returns_explicit_skipped_status(self):
        instance = make_instance([(2, 3), (3, 5)], 100)
        result = solve(instance, "dynamic_programming", max_dp_cells=10)
        self.assertEqual(result.status, "skipped")
        validate_result(instance, result)

    def test_tiny_time_budget_does_not_claim_optimality(self):
        instance = make_instance([(i + 1, 2 * i + 1) for i in range(30)], 200)
        for algorithm in ("brute_force", "dynamic_programming", "branch_and_bound"):
            result = solve(instance, algorithm, time_limit=1e-12)
            self.assertEqual(result.status, "timeout")
            validate_result(instance, result)

    def test_unknown_algorithm_rejected(self):
        with self.assertRaises(ValueError):
            solve(make_instance([], 0), "unknown")

    def test_invalid_time_limit_rejected(self):
        for value in (0, -1, float("inf"), float("nan"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                solve(make_instance([], 0), "greedy", time_limit=value)


class ModelTests(unittest.TestCase):
    """验证非法容量、重量、价值和重复编号会在建模阶段被拒绝。"""
    def test_invalid_capacity(self):
        for capacity in (-1, 1.5, True, "3"):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                make_instance([], capacity)

    def test_invalid_weight(self):
        for weight in (0, -2, 1.5, True):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                make_instance([(weight, 1)], 10)

    def test_invalid_value(self):
        for value in (-2, 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                make_instance([(1, value)], 10)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            Instance((Item("A", 1, 1), Item("A", 2, 2)), 10)

    def test_blank_id_rejected(self):
        with self.assertRaises(ValueError):
            Item(" ", 1, 1)


if __name__ == "__main__":
    unittest.main()
