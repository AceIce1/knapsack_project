"""定义物品、问题实例和求解结果，并独立校验输入与解的可行性。"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Item:
    """一件不可拆分的物品；编号唯一，重量为正整数，价值为非负整数。"""
    id: str
    weight: int
    value: int

    def __post_init__(self):
        """在创建对象时检查数据，明确拒绝布尔值和小数充当整数。"""
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Item id must be a nonblank string.")
        if type(self.weight) is not int or self.weight <= 0:
            raise ValueError("Weight must be a positive integer.")
        if type(self.value) is not int or self.value < 0:
            raise ValueError("Value must be a nonnegative integer.")


@dataclass(frozen=True)
class Instance:
    """一个完整的背包实例，由物品集合、容量和实例名称组成。"""
    items: tuple[Item, ...]
    capacity: int
    name: str = "custom"

    def __post_init__(self):
        """把物品集合转为不可变元组，并检查容量、元素类型和编号唯一性。"""
        object.__setattr__(self, "items", tuple(self.items))
        if type(self.capacity) is not int or self.capacity < 0:
            raise ValueError("Capacity must be a nonnegative integer.")
        if any(not isinstance(item, Item) for item in self.items):
            raise ValueError("All items must be Item objects.")
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("Item ids must be unique.")
        if not isinstance(self.name, str):
            raise ValueError("Instance name must be a string.")

    def to_dict(self):
        """转换成可由 JSON 序列化的字典。"""
        return asdict(self)


@dataclass(frozen=True)
class Result:
    """统一保存所选物品下标、总重量、总价值、耗时、工作量和求解状态。"""
    algorithm: str
    selected_indices: tuple[int, ...]
    total_weight: int
    total_value: int
    elapsed_ms: float
    status: str
    operations: int
    note: str = ""

    def to_dict(self, instance):
        """导出结果，并将内部下标转换为用户输入的物品编号。"""
        data = asdict(self)
        data["selected_ids"] = [instance.items[i].id for i in self.selected_indices]
        return data


def validate_result(instance: Instance, result: Result):
    """重新计算解的重量和价值；通过可行性检查不代表已经证明全局最优。"""
    indices = result.selected_indices
    if any(type(i) is not int or i < 0 or i >= len(instance.items) for i in indices):
        raise ValueError("Invalid selected item index.")
    if len(set(indices)) != len(indices):
        raise ValueError("An item was selected more than once.")
    weight = sum(instance.items[i].weight for i in indices)
    value = sum(instance.items[i].value for i in indices)
    if weight > instance.capacity:
        raise ValueError("Selected items exceed capacity.")
    if (weight, value) != (result.total_weight, result.total_value):
        raise ValueError("Reported totals disagree with selected items.")
    if result.status not in {"optimal", "heuristic", "timeout", "cancelled", "skipped"}:
        raise ValueError("Unknown result status.")
