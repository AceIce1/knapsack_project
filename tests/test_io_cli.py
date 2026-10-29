"""验证文件导入导出、随机数据复现和命令行完整执行流程。"""

import json
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

from knapsack.io import generate_instance, load_instance, save_instance, save_results
from knapsack.algorithms import solve


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def temporary_folder():
    """创建独立临时目录，并在测试结束后检查目录位置再清理。"""
    # 使用继承的目录权限，兼容受限 Windows 测试环境。
    parent = Path(tempfile.gettempdir()).resolve()
    folder = parent / f"knapsack-test-{uuid.uuid4().hex}"
    folder.mkdir()
    try:
        yield folder
    finally:
        if folder.resolve().parent != parent:
            raise RuntimeError("Unexpected test directory location.")
        shutil.rmtree(folder)


class IOTests(unittest.TestCase):
    """输入输出与命令行的集成测试，不依赖图形桌面。"""
    def test_json_round_trip(self):
        instance = generate_instance(5, 20, seed=7)
        with temporary_folder() as folder:
            path = Path(folder) / "case.json"
            save_instance(instance, path)
            self.assertEqual(load_instance(path), instance)

    def test_csv_and_capacity_override(self):
        with temporary_folder() as folder:
            path = Path(folder) / "case.csv"
            path.write_text("id,weight,value\nA,10,60\nB,20,100\n", encoding="utf-8-sig")
            instance = load_instance(path, capacity=25)
            self.assertEqual(instance.capacity, 25)
            self.assertEqual(len(instance.items), 2)

    def test_csv_requires_capacity(self):
        with temporary_folder() as folder:
            path = Path(folder) / "case.csv"
            path.write_text("id,weight,value\nA,1,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_instance(path)

    def test_json_does_not_silently_truncate_decimals(self):
        with temporary_folder() as folder:
            path = Path(folder) / "bad.json"
            path.write_text(json.dumps({"capacity": 3, "items": [{"id": "A", "weight": 1.9, "value": 4}]}))
            with self.assertRaises(ValueError):
                load_instance(path)

    def test_result_export_contains_input_and_selected_ids(self):
        instance = generate_instance(5, 20, seed=7)
        result = solve(instance, "dynamic_programming")
        with temporary_folder() as folder:
            path = Path(folder) / "result.json"
            save_results(instance, [result], path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["instance"]["capacity"], 20)
            self.assertIn("selected_ids", data["results"][0])

    def test_generator_is_reproducible(self):
        self.assertEqual(generate_instance(10, 40, 123), generate_instance(10, 40, 123))

    def test_invalid_generator_parameters(self):
        for n, capacity in [(-1, 10), (True, 10), (1, -1)]:
            with self.subTest(n=n, capacity=capacity), self.assertRaises(ValueError):
                generate_instance(n, capacity)

    def test_cli_demo_and_json_export(self):
        with temporary_folder() as folder:
            path = Path(folder) / "result.json"
            run = subprocess.run(
                [sys.executable, "-X", "utf8", "main.py", "solve",
                 "--input", "data/classic.json", "--output", str(path)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["results"]), 4)
            exact = [r for r in data["results"] if r["status"] == "optimal"]
            self.assertTrue(all(r["total_value"] == 220 for r in exact))

    def test_cli_invalid_input_exits_cleanly(self):
        run = subprocess.run(
            [sys.executable, "-X", "utf8", "main.py", "solve", "--input", "does_not_exist.json"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(run.returncode, 2)
        self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
