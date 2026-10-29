"""项目入口：直接运行启动桌面界面，也可通过子命令求解、生成数据或执行实验。"""

import argparse
from pathlib import Path
import sys

from knapsack.algorithms import ALGORITHMS, STATUS_LABELS, solve
from knapsack.io import generate_instance, load_instance, save_instance, save_results


def make_parser():
    """定义命令行参数；不传子命令时默认启动中文桌面界面。"""
    parser = argparse.ArgumentParser(description="0/1 背包优化算法对比")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("gui", help="启动桌面界面")
    solver = commands.add_parser("solve", help="求解 JSON 或 CSV 实例")
    solver.add_argument("--input", default=str(Path(__file__).parent / "data" / "classic.json"))
    solver.add_argument("--capacity", type=int)
    solver.add_argument("--algorithm", choices=["all", *ALGORITHMS], default="all")
    solver.add_argument("--time-limit", type=float, default=5.0)
    solver.add_argument("--output")
    generator = commands.add_parser("generate", help="生成可复现的随机实例")
    generator.add_argument("--n", type=int, default=20)
    generator.add_argument("--capacity", type=int, default=120)
    generator.add_argument("--seed", type=int, default=20261029)
    generator.add_argument("--output", required=True)
    benchmark = commands.add_parser("benchmark", help="运行批量实验并导出 CSV/JSON/SVG")
    benchmark.add_argument("--output", default="results/reproduced")
    benchmark.add_argument("--time-limit", type=float, default=0.5)
    benchmark.add_argument("--trials", type=int, default=3)
    return parser


def main(argv=None):
    """解析参数并分派任务，返回供操作系统判断执行结果的退出码。"""
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "gui"):
            # 延迟导入界面模块，使没有安装 Tk 的环境仍然可以运行算法和实验。
            from knapsack.gui import launch
            launch()
        elif args.command == "generate":
            save_instance(generate_instance(args.n, args.capacity, args.seed), args.output)
            print(f"已生成: {args.output}")
        elif args.command == "solve":
            instance = load_instance(args.input, args.capacity)
            names = list(ALGORITHMS) if args.algorithm == "all" else [args.algorithm]
            results = [solve(instance, name, args.time_limit) for name in names]
            print(f"实例: {instance.name} | 物品数: {len(instance.items)} | 容量: {instance.capacity}")
            for result in results:
                ids = ",".join(instance.items[i].id for i in result.selected_indices) or "-"
                print(f"{ALGORITHMS[result.algorithm]} | 价值 {result.total_value} | "
                      f"重量 {result.total_weight} | {result.elapsed_ms:.3f} ms | "
                      f"{STATUS_LABELS[result.status]} | 选择 {ids}")
                if result.note:
                    print(f"  {result.note}")
            if args.output:
                save_results(instance, results, args.output)
                print(f"已导出: {args.output}")
        elif args.command == "benchmark":
            from knapsack.experiments import run_benchmarks
            run_benchmarks(args.output, args.time_limit, args.trials)
    except (ValueError, OSError, MemoryError, RuntimeError, ImportError) as error:
        print(f"错误: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已中止。", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
