"""验证实验统计正确区分已完成求解与超时观测。"""

import unittest

from knapsack.experiments import summarize


class ExperimentTests(unittest.TestCase):
    """检查超时计数、完成组中位数以及没有最优基准时的缺失值。"""
    def test_timeout_is_not_counted_as_proved_optimal(self):
        rows = [
            dict(experiment="n_scale", n=20, capacity=120, algorithm="brute_force",
                 elapsed_ms=10, status="optimal", value_ratio=1),
            dict(experiment="n_scale", n=20, capacity=120, algorithm="brute_force",
                 elapsed_ms=500, status="timeout", value_ratio=0.9),
        ]
        summary = summarize(rows)[0]
        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["optimal_runs"], 1)
        self.assertEqual(summary["timeout_runs"], 1)
        self.assertEqual(summary["median_ms_completed"], 10)
        self.assertEqual(summary["median_ms_all"], 255)

    def test_empty_completed_group_has_no_fake_zero_runtime(self):
        rows = [
            dict(experiment="n_scale", n=24, capacity=120, algorithm="brute_force",
                 elapsed_ms=500, status="timeout", value_ratio=None)
        ]
        summary = summarize(rows)[0]
        self.assertIsNone(summary["median_ms_completed"])
        self.assertIsNone(summary["mean_value_ratio"])


if __name__ == "__main__":
    unittest.main()
