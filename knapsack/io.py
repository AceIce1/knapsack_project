"""读取和保存 JSON/CSV 数据，并通过固定随机种子生成可复现实验实例。"""

import csv
import json
from pathlib import Path
import random

from .models import Instance, Item, validate_result


def load_instance(path, capacity=None):
    """读取实例；CSV 必须另外提供容量，JSON 可使用文件容量或显式覆盖值。"""
    path = Path(path)
    try:
        if path.suffix.lower() == ".csv":
            if capacity is None:
                raise ValueError("CSV input requires --capacity.")
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != ["id", "weight", "value"]:
                    raise ValueError("CSV header must be id,weight,value.")
                items = tuple(Item(row["id"], int(row["weight"]), int(row["value"])) for row in reader)
            return Instance(items, capacity, path.stem)
        if path.suffix.lower() != ".json":
            raise ValueError("Only .json and .csv input files are supported.")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("JSON must contain an items array.")
        items = tuple(Item(row["id"], row["weight"], row["value"]) for row in data["items"])
        return Instance(items, data["capacity"] if capacity is None else capacity, data.get("name", path.stem))
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"Invalid input structure: {error}") from error


def save_instance(instance, path):
    """以 UTF-8 编码保存完整实例，必要时创建父目录。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(instance.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def save_results(instance, results, path):
    """先检查各解的可行性，再将原始输入与所有结果一同导出。"""
    for result in results:
        validate_result(instance, result)
    data = {"instance": instance.to_dict(), "results": [r.to_dict(instance) for r in results]}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_instance(n=20, capacity=120, seed=20261029, max_weight=30, max_value=100):
    """生成重量和价值相互独立的均匀整数随机实例，相同参数产生相同数据。"""
    if type(n) is not int or n < 0 or n > 10_000:
        raise ValueError("Item count must be an integer from 0 to 10,000.")
    if type(capacity) is not int or capacity < 0:
        raise ValueError("Capacity must be a nonnegative integer.")
    if type(max_weight) is not int or max_weight < 1 or type(max_value) is not int or max_value < 1:
        raise ValueError("Maximum weight and value must be positive integers.")
    if type(seed) is not int:
        raise ValueError("Random seed must be an integer.")
    rng = random.Random(seed)
    items = tuple(Item(f"I{i + 1:03}", rng.randint(1, max_weight), rng.randint(1, max_value)) for i in range(n))
    return Instance(items, capacity, f"random_n{n}_c{capacity}_seed{seed}")
