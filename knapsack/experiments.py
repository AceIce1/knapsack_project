"""执行可复现实验，保留完整输入、原始运行数据和超时记录，避免只报告成功结果。"""

from collections import defaultdict
from datetime import datetime, timezone
import csv
import json
import math
import os
from pathlib import Path
import platform
import random
from statistics import mean, median
import sys
import xml.etree.ElementTree as ET

from .algorithms import ALGORITHMS, solve
from .io import generate_instance


SHORT_NAMES = {
    "greedy": "Greedy", "dynamic_programming": "DP",
    "branch_and_bound": "Branch & bound", "brute_force": "Exhaustive",
}
COLORS = {
    "greedy": "#b04b35", "dynamic_programming": "#247854",
    "branch_and_bound": "#3c6eb4", "brute_force": "#925b9d",
}


def summarize(rows):
    """按实验类型、物品数、容量和算法分组，分别统计完成耗时与超时次数。"""
    groups = defaultdict(list)
    for row in rows:
        groups[(row["experiment"], row["n"], row["capacity"], row["algorithm"])].append(row)
    output = []
    for key, group in sorted(groups.items()):
        completed = [r["elapsed_ms"] for r in group if r["status"] in ("optimal", "heuristic")]
        # 超时属于未完成观测，不能把其耗时当作算法完整求解时间参与完成组统计。
        quality = [r["value_ratio"] for r in group if r["value_ratio"] is not None]
        output.append(dict(
            zip(("experiment", "n", "capacity", "algorithm"), key),
            runs=len(group),
            optimal_runs=sum(r["status"] == "optimal" for r in group),
            timeout_runs=sum(r["status"] == "timeout" for r in group),
            median_ms_all=median(r["elapsed_ms"] for r in group),
            median_ms_completed=median(completed) if completed else None,
            mean_value_ratio=mean(quality) if quality else None,
        ))
    return output


def _write_csv(path, rows):
    """写入带 UTF-8 字节顺序标记的 CSV，便于常见表格软件直接识别中文。"""
    if not rows:
        return
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def runtime_svg(summary, experiment, x_key, path, title):
    """使用标准库生成独立 SVG 曲线，超时结果保留在原始表格而不伪装成完成点。"""
    rows = [r for r in summary if r["experiment"] == experiment]
    xs = sorted({r[x_key] for r in rows})
    times = [r["median_ms_completed"] for r in rows if r["median_ms_completed"] is not None]
    if not xs or not times:
        return
    low = math.floor(math.log10(max(min(times), 0.000001))) - 1
    high = max(low + 1, math.ceil(math.log10(max(times))))
    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width="960", height="520",
                     viewBox="0 0 960 520")

    def element(tag, **attrs):
        return ET.SubElement(svg, tag, {k.replace("_", "-"): str(v) for k, v in attrs.items()})

    def text(x, y, content, **attrs):
        node = element("text", x=x, y=y, fill="#20252b", font_family="Arial", font_size=14, **attrs)
        node.text = str(content)

    element("rect", width=960, height=520, fill="white")
    text(70, 35, title, font_weight="bold")
    text(70, 59, "Median completed runs only; timeouts are recorded separately in raw.csv.")

    def xpos(value):
        return 95 + xs.index(value) * 610 / max(1, len(xs) - 1)

    def ypos(value):
        return 420 - (math.log10(max(value, 0.000001)) - low) * 310 / (high - low)

    for exponent in range(low, high + 1):
        y = ypos(10**exponent)
        element("line", x1=95, y1=y, x2=705, y2=y, stroke="#e2e5e8")
        text(85, y + 5, f"{10**exponent:g}", text_anchor="end")
    for x in xs:
        text(xpos(x), 448, x, text_anchor="middle")
    text(400, 480, "Item count n" if x_key == "n" else "Capacity C", text_anchor="middle")
    text(20, 90, "ms")
    for position, algorithm in enumerate(ALGORITHMS):
        series = sorted((r for r in rows if r["algorithm"] == algorithm), key=lambda r: r[x_key])
        if not series:
            continue
        segment = []
        segments = []
        for row in series:
            value = row["median_ms_completed"]
            if value is None:
                if segment:
                    segments.append(segment)
                    segment = []
                continue
            x, y = xpos(row[x_key]), ypos(value)
            segment.append(f"{x:.1f},{y:.1f}")
            element("circle", cx=x, cy=y, r=4, fill=COLORS[algorithm])
        if segment:
            segments.append(segment)
        for segment in segments:
            element("polyline", points=" ".join(segment), fill="none",
                    stroke=COLORS[algorithm], stroke_width=2)
        y = 120 + position * 32
        element("line", x1=755, y1=y, x2=780, y2=y, stroke=COLORS[algorithm], stroke_width=3)
        text(790, y + 5, SHORT_NAMES[algorithm])
    ET.ElementTree(svg).write(path, encoding="utf-8", xml_declaration=True)


def run_benchmarks(output, time_limit=0.5, trials=3):
    """依次运行物品数、容量和解质量实验，导出原始数据、统计和曲线。"""
    if type(trials) is not int or not 1 <= trials <= 20:
        raise ValueError("Trials must be an integer from 1 to 20.")
    if not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError("Time limit must be finite and positive.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    base_seed = 20261029
    # 第一组固定容量，改变物品数；相同种子使较小实例成为较大实例的前缀。
    for n in (8, 12, 16, 20, 24):
        for trial in range(trials):
            cases.append(("n_scale", base_seed + trial, generate_instance(n, 120, base_seed + trial), True))
    for capacity in (100, 300, 600, 1200, 2400):
        # 第二组固定物品数，同一种子在不同容量下严格使用同一批物品。
        for trial in range(trials):
            seed = base_seed + 100 + trial
            cases.append(("capacity_scale", seed, generate_instance(60, capacity, seed, 80, 100), False))
    for trial in range(20):
        seed = base_seed + 1000 + trial
        cases.append(("quality", seed, generate_instance(60, 300, seed), False))
    # 正式计时前运行小实例预热，不把预热结果计入实验记录。
    warmup = generate_instance(6, 20, 1)
    for algorithm in ALGORITHMS:
        solve(warmup, algorithm)
    rows, manifest = [], []
    for number, (experiment, seed, instance, include_brute) in enumerate(cases, 1):
        names = list(ALGORITHMS) if include_brute else [a for a in ALGORITHMS if a != "brute_force"]
        # 固定种子打乱运行顺序，降低每次都先运行同一算法造成的顺序偏差。
        random.Random(seed + len(instance.items) + instance.capacity).shuffle(names)
        results = [solve(instance, name, time_limit) for name in names]
        proven = {r.total_value for r in results if r.status == "optimal"}
        # 只有完整运行的精确算法才能提供最优值基准；无证明时质量比留空。
        if len(proven) > 1:
            raise AssertionError("Exact algorithms disagree; experiment aborted.")
        optimum = next(iter(proven)) if proven else None
        case_id = f"{experiment}_{number:03}"
        manifest.append({"case_id": case_id, "seed": seed, "instance": instance.to_dict()})
        for result in results:
            ratio = None if optimum is None else (result.total_value / optimum if optimum else 1.0)
            rows.append(dict(
                case_id=case_id, experiment=experiment, n=len(instance.items),
                capacity=instance.capacity, seed=seed, algorithm=result.algorithm,
                total_value=result.total_value, total_weight=result.total_weight,
                elapsed_ms=result.elapsed_ms, status=result.status, operations=result.operations,
                optimum=optimum, value_ratio=ratio,
                selected_ids=";".join(instance.items[i].id for i in result.selected_indices),
            ))
        print(f"[{number:02}/{len(cases)}] {experiment}: n={len(instance.items)}, C={instance.capacity}", flush=True)
    summary = summarize(rows)
    metadata = {
        # 元数据明确记录计时范围、随机分布和穷举适用范围，方便他人复核。
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(),
        "processor": platform.processor(), "logical_cpu_count": os.cpu_count(),
        "time_limit_seconds": time_limit, "trials_per_scale": trials, "base_seed": base_seed,
        "quality_cases": 20, "instance_count": len(cases), "run_count": len(rows),
        "timing": "perf_counter_ns; solver including sorting/reconstruction, excluding I/O and result validation",
        "timeout_policy": "Cooperative checks; censored runs are not completed-run timing samples.",
        "brute_force_policy": "Only n_scale cases; omitted for n=60, not recorded as a timeout.",
        "distribution": "Independent uniform integer weights and values; see manifest for all exact inputs.",
    }
    _write_csv(output / "raw.csv", rows)
    _write_csv(output / "summary.csv", summary)
    for name, data in (("metadata.json", metadata), ("instances.json", manifest), ("summary.json", summary)):
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    runtime_svg(summary, "n_scale", "n", output / "n_runtime.svg", "Runtime versus item count (C = 120)")
    runtime_svg(summary, "capacity_scale", "capacity", output / "capacity_runtime.svg",
                "Runtime versus capacity (n = 60)")
    print(f"实验完成，共 {len(cases)} 个实例、{len(rows)} 次求解。输出: {output}")
    return rows, summary, metadata
