"""中文 Tk 桌面界面；后台线程只负责计算，不直接访问界面控件。

线程模型参考：https://docs.python.org/3.12/library/tkinter.html#threading-model
"""

from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .algorithms import ALGORITHMS, STATUS_LABELS, solve
from .io import generate_instance, load_instance, save_instance, save_results
from .models import Instance, Item


class KnapsackApp:
    """管理实例编辑、算法运行、取消操作、结果选择和可视化状态。"""
    def __init__(self, root):
        self.root = root
        self.root.title("背包优化实验室")
        width = max(960, min(1180, self.root.winfo_screenwidth() - 80))
        height = max(700, min(800, self.root.winfo_screenheight() - 100))
        self.root.geometry(f"{width}x{height}+20+20")
        self.root.minsize(960, 700)
        self.busy = False
        self.cancel_event = threading.Event()
        self.messages = Queue()
        self.results = []
        self.editable = []
        self.instance = load_instance(Path(__file__).resolve().parents[1] / "data" / "classic.json")
        self.capacity = tk.StringVar(value="50")
        self.count = tk.StringVar(value="20")
        self.seed = tk.StringVar(value="20261029")
        self.seconds = tk.StringVar(value="5")
        self.algorithm = tk.StringVar(value="全部算法")
        self.item_id = tk.StringVar()
        self.weight = tk.StringVar()
        self.value = tk.StringVar()
        self.status = tk.StringVar(value="就绪")
        self.selection_text = tk.StringVar(value="尚无求解结果")
        self.usage_text = tk.StringVar(value="容量使用率 0%")
        self._build()
        self._refresh_items()
        self.capacity.trace_add("write", lambda *_: self._invalidate())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(60, self._poll)

    def _track(self, widget):
        self.editable.append(widget)
        return widget

    def _button(self, parent, text, command):
        return self._track(ttk.Button(parent, text=text, command=command))

    def _entry(self, parent, variable, width=9):
        return self._track(ttk.Entry(parent, textvariable=variable, width=width))

    def _build(self):
        """创建左右分栏布局，分别显示物品编辑区与算法结果区。"""
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10), background="#f4f5f6", foreground="#25282c")
        style.configure("TButton", padding=(10, 6))
        style.configure("Treeview", background="white", fieldbackground="white", rowheight=30)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"), padding=6)
        style.map("Treeview", background=[("selected", "#d7eade")], foreground=[("selected", "#163d2d")])
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Section.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="背包优化实验室", style="Title.TLabel").pack(anchor="w")
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(16, 12))
        for text, command in (("导入实例", self.import_data), ("保存实例", self.save_data),
                              ("经典反例", self.classic), ("生成实例", self.generate)):
            self._button(toolbar, text, command).pack(side="left", padx=(0, 8))
        self.export_button = ttk.Button(toolbar, text="导出结果", command=self.export, state="disabled")
        self.export_button.pack(side="right")
        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 16))
        for title, variable, width in (("容量", self.capacity, 8), ("物品数", self.count, 6),
                                       ("随机种子", self.seed, 12), ("每算法限时 秒", self.seconds, 6)):
            ttk.Label(controls, text=title).pack(side="left", padx=(0, 6))
            self._entry(controls, variable, width).pack(side="left", padx=(0, 14))
        combo = self._track(ttk.Combobox(controls, textvariable=self.algorithm, state="readonly",
                                       values=["全部算法", *ALGORITHMS.values()], width=16))
        combo.pack(side="left", padx=(0, 8))
        self.run_button = self._button(controls, "开始求解", self.run)
        self.run_button.pack(side="left")
        self.cancel_button = ttk.Button(controls, text="取消", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(8, 0))
        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        panes.add(left, weight=4)
        panes.add(right, weight=6)
        self.items_title = ttk.Label(left, style="Section.TLabel")
        self.items_title.pack(anchor="w", pady=(0, 10))
        item_frame = ttk.Frame(left)
        item_frame.pack(fill="both", expand=True, padx=(0, 16))
        self.item_table = ttk.Treeview(item_frame, columns=("id", "weight", "value", "ratio"),
                                       show="headings", selectmode="extended")
        for key, label, width in (("id", "物品", 100), ("weight", "重量", 65),
                                  ("value", "价值", 70), ("ratio", "价值重量比", 100)):
            self.item_table.heading(key, text=label)
            self.item_table.column(key, width=width, minwidth=55, anchor="center")
        scrollbar = ttk.Scrollbar(item_frame, orient="vertical", command=self.item_table.yview)
        self.item_table.configure(yscrollcommand=scrollbar.set)
        self.item_table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.item_table.tag_configure("chosen", background="#e2f0e7")
        self.item_table.bind("<<TreeviewSelect>>", self._fill_editor)
        editor = ttk.Frame(left)
        editor.pack(fill="x", pady=(12, 8))
        for label, variable, width in (("编号", self.item_id, 10), ("重量", self.weight, 7), ("价值", self.value, 7)):
            ttk.Label(editor, text=label).pack(side="left", padx=(0, 4))
            self._entry(editor, variable, width).pack(side="left", padx=(0, 8))
        actions = ttk.Frame(left)
        actions.pack(fill="x")
        for label, command in (("添加", self.add_item), ("更新所选", self.update_item), ("删除所选", self.remove_items)):
            self._button(actions, label, command).pack(side="left", padx=(0, 8))
        ttk.Label(right, text="算法结果", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        result_frame = ttk.Frame(right)
        result_frame.grid(row=1, column=0, sticky="ew")
        self.result_table = ttk.Treeview(result_frame, columns=("algorithm", "value", "weight", "ms", "status"),
                                         show="headings", height=4, selectmode="browse")
        for key, label, width in (("algorithm", "算法", 125), ("value", "总价值", 65),
                                  ("weight", "总重量", 65), ("ms", "耗时 ms", 80), ("status", "求解状态", 120)):
            self.result_table.heading(key, text=label)
            self.result_table.column(key, width=width, minwidth=55, anchor="center")
        self.result_table.pack(fill="x")
        self.result_table.bind("<<TreeviewSelect>>", self._select_result)
        self.chart = tk.Canvas(right, background="white", highlightthickness=0, height=140)
        self.chart.grid(row=2, column=0, sticky="nsew", pady=(14, 12))
        self.chart.bind("<Configure>", lambda _: self._draw_chart())
        ttk.Label(right, textvariable=self.usage_text).grid(row=3, column=0, sticky="w")
        self.usage = ttk.Progressbar(right, maximum=100)
        self.usage.grid(row=4, column=0, sticky="ew", pady=(6, 8))
        self.detail = ttk.Label(right, textvariable=self.selection_text, wraplength=500, anchor="nw")
        self.detail.grid(row=5, column=0, sticky="ew")
        self.detail.bind("<Configure>", lambda e: self.detail.configure(wraplength=max(100, e.width - 4)))
        ttk.Separator(outer).pack(fill="x", pady=(16, 10))
        ttk.Label(outer, textvariable=self.status).pack(anchor="w")

    def _invalidate(self):
        """数据变化后清空旧结果，防止展示或导出与当前输入不一致的解。"""
        if self.busy:
            return
        self.results.clear()
        self.result_table.delete(*self.result_table.get_children())
        self.export_button.state(["disabled"])
        self.selection_text.set("尚无求解结果")
        self.usage_text.set("容量使用率 0%")
        self.usage["value"] = 0
        for row in self.item_table.get_children():
            self.item_table.item(row, tags=())
        self._draw_chart()

    def _refresh_items(self):
        """用当前实例重建物品表格，并同步数量与结果状态。"""
        self.item_table.delete(*self.item_table.get_children())
        for i, item in enumerate(self.instance.items):
            self.item_table.insert("", "end", iid=str(i),
                                   values=(item.id, item.weight, item.value, f"{item.value / item.weight:.2f}"))
        self.items_title.configure(text=f"物品列表  {len(self.instance.items)}")
        self._invalidate()

    def _current(self):
        """将容量输入与当前物品集合组合成一个重新校验过的实例。"""
        return Instance(self.instance.items, int(self.capacity.get()), self.instance.name)

    def _replace(self, instance):
        """替换整个实例，供导入、随机生成和物品编辑共用。"""
        self.instance = instance
        self.capacity.set(str(instance.capacity))
        self._refresh_items()
        self.status.set(f"已载入 {instance.name}，共 {len(instance.items)} 件物品")

    def classic(self):
        """载入能说明贪心不保证最优的经典三物品反例。"""
        self._replace(load_instance(Path(__file__).resolve().parents[1] / "data" / "classic.json"))

    def generate(self):
        """读取物品数、容量和种子，生成适合桌面表格显示的随机实例。"""
        try:
            n = int(self.count.get())
            if n > 1000:
                raise ValueError("桌面表格最多生成1000件物品，较大实例请使用命令行。")
            self._replace(generate_instance(n, int(self.capacity.get()), int(self.seed.get())))
        except ValueError as error:
            messagebox.showerror("输入错误", str(error))

    def import_data(self):
        """导入 JSON 或 CSV；CSV 的容量使用界面当前输入值。"""
        path = filedialog.askopenfilename(filetypes=[("实例", "*.json *.csv"), ("JSON", "*.json"), ("CSV", "*.csv")])
        if path:
            try:
                override = int(self.capacity.get()) if Path(path).suffix.lower() == ".csv" else None
                self._replace(load_instance(path, override))
            except (ValueError, OSError) as error:
                messagebox.showerror("导入失败", str(error))

    def save_data(self):
        """保存当前实例，不包含旧输入或历史求解结果。"""
        try:
            instance = self._current()
            path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
            if path:
                save_instance(instance, path)
                self.status.set("实例已保存")
        except (ValueError, OSError) as error:
            messagebox.showerror("保存失败", str(error))

    def _fill_editor(self, _=None):
        """选择表格行后，将对应物品内容填入编辑区。"""
        selected = self.item_table.selection()
        if selected:
            item = self.instance.items[int(selected[0])]
            self.item_id.set(item.id)
            self.weight.set(str(item.weight))
            self.value.set(str(item.value))

    def _edited_item(self):
        """把编辑区内容转换成经过验证的物品对象。"""
        return Item(self.item_id.get().strip(), int(self.weight.get()), int(self.value.get()))

    def add_item(self):
        """添加一件物品，重复编号或非法数值由数据模型拒绝。"""
        try:
            item = self._edited_item()
            self._replace(Instance((*self.instance.items, item), int(self.capacity.get()), "custom"))
        except ValueError as error:
            messagebox.showerror("输入错误", str(error))

    def update_item(self):
        """只更新恰好选中的一件物品，避免多选时修改对象不明确。"""
        selected = self.item_table.selection()
        if len(selected) != 1:
            messagebox.showinfo("选择物品", "请选择一件物品。")
            return
        try:
            items = list(self.instance.items)
            items[int(selected[0])] = self._edited_item()
            self._replace(Instance(tuple(items), int(self.capacity.get()), "custom"))
        except ValueError as error:
            messagebox.showerror("输入错误", str(error))

    def remove_items(self):
        """删除选中的物品；未选中的物品保持原有顺序。"""
        selected = {int(i) for i in self.item_table.selection()}
        if selected:
            try:
                items = tuple(item for i, item in enumerate(self.instance.items) if i not in selected)
                self._replace(Instance(items, int(self.capacity.get()), "custom"))
            except ValueError as error:
                messagebox.showerror("输入错误", str(error))

    def _set_busy(self, busy):
        """计算时锁定输入控件，只保留取消操作，避免后台结果与输入错配。"""
        self.busy = busy
        for widget in self.editable:
            widget.state(["disabled"] if busy else ["!disabled"])
        self.cancel_button.state(["!disabled"] if busy else ["disabled"])
        self.export_button.state(["!disabled"] if self.results and not busy else ["disabled"])

    def run(self):
        """先固定本次输入快照，再在工作线程中依次运行所选算法。"""
        if self.busy:
            return
        try:
            instance = self._current()
            seconds = float(self.seconds.get())
            if not 0 < seconds <= 300:
                raise ValueError("限时应大于0且不超过300秒。")
        except ValueError as error:
            messagebox.showerror("输入错误", str(error))
            return
        names = list(ALGORITHMS) if self.algorithm.get() == "全部算法" else [
            next(key for key, label in ALGORITHMS.items() if label == self.algorithm.get())]
        self._invalidate()
        self.instance = instance
        self.cancel_event = threading.Event()
        self._set_busy(True)
        self.status.set("求解中")

        def worker():
            """只通过队列发送结果、异常和结束事件，不在子线程中操作 Tk。"""
            try:
                for name in names:
                    if self.cancel_event.is_set():
                        break
                    result = solve(instance, name, seconds, self.cancel_event)
                    self.messages.put(("result", result))
            except Exception as error:
                self.messages.put(("error", str(error)))
            finally:
                self.messages.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    def cancel(self):
        """设置取消事件，算法在下一次预算检查时主动停止。"""
        self.cancel_event.set()
        self.cancel_button.state(["disabled"])
        self.status.set("正在取消")

    def _poll(self):
        """主线程定时取出队列事件，安全更新表格、图表和运行状态。"""
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "result":
                    self.results.append(payload)
                    self.result_table.insert("", "end", iid=payload.algorithm, values=(
                        ALGORITHMS[payload.algorithm], payload.total_value, payload.total_weight,
                        f"{payload.elapsed_ms:.3f}", STATUS_LABELS[payload.status]))
                    self.result_table.selection_set(payload.algorithm)
                    self._select_result()
                    self._draw_chart()
                elif kind == "error":
                    messagebox.showerror("求解失败", payload)
                elif kind == "done":
                    self._set_busy(False)
                    self.status.set("已取消" if self.cancel_event.is_set() else "求解完成，结果已通过可行性校验")
        except Empty:
            pass
        self.root.after(60, self._poll)

    def _select_result(self, _=None):
        """切换算法结果时，同步高亮物品并更新容量使用率和选择说明。"""
        selected = self.result_table.selection()
        if not selected:
            return
        result = next(r for r in self.results if r.algorithm == selected[0])
        chosen = set(result.selected_indices)
        for i in range(len(self.instance.items)):
            self.item_table.item(str(i), tags=("chosen",) if i in chosen else ())
        ids = [self.instance.items[i].id for i in result.selected_indices]
        visible = "、".join(ids[:40]) or "空集"
        if len(ids) > 40:
            visible += f" 等{len(ids)}件"
        ratio = 100 * result.total_weight / self.instance.capacity if self.instance.capacity else 0
        self.usage["value"] = ratio
        self.usage_text.set(f"容量使用率 {ratio:.1f}%   剩余容量 {self.instance.capacity - result.total_weight}")
        self.selection_text.set(f"所选物品：{visible}\n{STATUS_LABELS[result.status]}"
                                + (f"\n{result.note}" if result.note else ""))

    def _draw_chart(self):
        """按当前画布大小绘制总价值条形图，颜色之外同时保留文字与数值。"""
        self.chart.delete("all")
        width = max(self.chart.winfo_width(), 300)
        height = max(self.chart.winfo_height(), 80)
        self.chart.create_text(16, 18, text="总价值对比", anchor="w",
                               font=("Microsoft YaHei UI", 11, "bold"), fill="#25282c")
        if not self.results:
            return
        colors = {"greedy": "#b04b35", "dynamic_programming": "#247854",
                  "branch_and_bound": "#3c6eb4", "brute_force": "#925b9d"}
        max_value = max(1, *(r.total_value for r in self.results))
        step = min(42, (height - 44) / max(1, len(self.results)))
        bar_height = max(4, min(20, step - 5))
        for i, result in enumerate(self.results):
            y = 44 + i * step
            self.chart.create_text(14, y + bar_height / 2, text=ALGORITHMS[result.algorithm], anchor="w",
                                   font=("Microsoft YaHei UI", 9))
            end = 135 + (width - 215) * result.total_value / max_value
            self.chart.create_rectangle(135, y, end, y + bar_height, fill=colors[result.algorithm], outline="")
            self.chart.create_text(end + 8, y + bar_height / 2, text=str(result.total_value), anchor="w",
                                   font=("Microsoft YaHei UI", 9))

    def export(self):
        """导出当前输入快照及本轮所有算法结果。"""
        if not self.results:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                save_results(self.instance, self.results, path)
                self.status.set("结果已导出")
            except (ValueError, OSError) as error:
                messagebox.showerror("导出失败", str(error))

    def close(self):
        """关闭窗口前发出取消信号，防止继续执行不需要的长时间搜索。"""
        self.cancel_event.set()
        self.root.destroy()


def launch():
    """创建 Tk 主窗口并进入事件循环，没有图形环境时给出明确错误。"""
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError("无法启动图形界面。请检查Tk安装，或使用命令行 solve 子命令。") from error
    KnapsackApp(root)
    root.mainloop()
