"""可选的真实 Tk 界面冒烟测试，需要在具有图形桌面的计算机上执行。"""

from pathlib import Path
import sys
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knapsack.gui import KnapsackApp
from knapsack.io import generate_instance, save_results
from knapsack.models import validate_result


def wait_until_idle(root, app, timeout=10):
    """持续处理界面事件，直到后台线程完成或达到测试等待上限。"""
    deadline = time.monotonic() + timeout
    while app.busy and time.monotonic() < deadline:
        root.update()
        time.sleep(0.02)
    assert not app.busy, "GUI worker did not finish."


def main():
    """验证增删改、求解、结果切换、输入失效、取消和错误提示等完整流程。"""
    root = tk.Tk()
    app = KnapsackApp(root)
    root.update()
    try:
        # 先执行真实控件操作，核对每一步操作后的物品数据。
        app.item_id.set("D")
        app.weight.set("5")
        app.value.set("7")
        app.add_item()
        assert len(app.instance.items) == 4
        app.item_table.selection_set("3")
        root.update()
        app.value.set("9")
        app.update_item()
        assert app.instance.items[3].value == 9
        app.item_table.selection_set("3")
        app.remove_items()
        assert len(app.instance.items) == 3
        app.classic()
        app.run()
        wait_until_idle(root, app)
        assert len(app.results) == 4
        assert sorted(r.total_value for r in app.results) == [160, 220, 220, 220]
        for result in app.results:
            validate_result(app.instance, result)
            app.result_table.selection_set(result.algorithm)
            root.update()
            app._select_result()
        app.capacity.set("40")
        # 改动输入后，旧算法结果必须立即失效，不能继续沿用。
        assert not app.results, "Changing capacity must invalidate old results."
        app.classic()
        app.algorithm.set("穷举搜索")
        app._replace(generate_instance(40, 500, 3))
        app.seconds.set("5")
        app.run()
        root.update()
        app.cancel()
        wait_until_idle(root, app)
        assert all(r.status != "optimal" for r in app.results)
        with patch("knapsack.gui.messagebox.showerror") as error:
            # 这里只替换阻塞式错误对话框，算法与界面状态仍使用真实实现。
            app.capacity.set("-1")
            app.run()
            error.assert_called_once()
        app.classic()
        app.algorithm.set("全部算法")
        app.run()
        wait_until_idle(root, app)
        output = Path(__file__).resolve().parents[1] / "results" / "gui_smoke_result.json"
        save_results(app.instance, app.results, output)
        print("GUI smoke passed: add/update/delete, solve, select, invalidate, cancel, invalid input.")
    finally:
        app.close()


if __name__ == "__main__":
    main()
