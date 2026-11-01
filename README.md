# 背包优化问题

这是一个可离线运行的 Python 0/1 背包优化项目，包含四种算法、中文桌面界面、
命令行工具、自动测试和可复现的规模对比实验。报告见交付目录中的 Word 文档，
报告正文源文件见 `docs/report.md`。所有 Python 代码的注释和文档字符串均为中文，
英文变量名、函数名及算法标识保持不变，便于运行和检索。

## 1 运行环境

- Python 3.10 或更高版本，Windows、macOS、Linux 均可使用命令行。
- 算法、实验、测试和界面均只使用 Python 标准库，不需要 pip 安装依赖。
- 桌面界面需要 Tk。Windows 官方 Python 安装时勾选 Tcl/Tk；
  Linux 请通过系统软件包管理器安装与 Python 对应的 Tk 组件。
- 检查图形环境：`python -m tkinter`。没有图形桌面时请使用命令行。

所有命令都在本 README 所在目录执行。

## 2 快速开始

```bash
python main.py
```

界面可生成随机数据、导入 JSON/CSV、添加/更新/删除物品、选择算法、设置每算法限时、
取消计算、查看所选物品与容量利用率，并导出完整求解结果。
CSV 的容量取界面当前输入值；JSON 使用文件中的容量。
改变容量或物品后，旧结果会清空，防止错误导出。

命令行运行经典反例：

```bash
python main.py solve --input data/classic.json --output results/classic_result.json
```

经典实例容量 50，A=(10,60)、B=(20,100)、C=(30,120)。
价值重量比贪心选择 A+B，总价值160；三个完整运行的精确算法得到 B+C，总价值220。

## 3 常用命令

```bash
# 使用动态规划求解 CSV 示例，将背包容量设为 10，并在终端显示结果。
python main.py solve --input data/demo.csv --capacity 10 --algorithm dynamic_programming

# 生成包含 30 个物品、容量为 160 的随机实例，固定种子为 42，保存到指定 JSON 文件。
python main.py generate --n 30 --capacity 160 --seed 42 --output data/random30.json

# 使用全部四种算法求解上述随机实例，每个算法限时 2 秒，并将结果导出到指定 JSON 文件。
python main.py solve --input data/random30.json --time-limit 2 --output results/random30.json

# 运行规模与解质量对比实验：每个规模使用 3 个随机实例，每个算法限时 0.5 秒；
# 将原始数据、统计结果和 SVG 曲线导出到 results/reproduced 目录。
python main.py benchmark --output results/reproduced --time-limit 0.5 --trials 3

# 自动发现并运行 tests 目录中的单元测试，逐项显示测试名称和结果。
python -m unittest discover -s tests -v

# 运行真实桌面界面冒烟测试，检查物品增删改、求解、结果切换、取消和错误提示等流程，需要图形桌面。
python scripts/gui_smoke.py
```

最后一条为可选的真实桌面交互测试，需要图形桌面。普通自动测试不依赖 Tk 和网络。
不同操作系统可能使用 `python3` 或 Windows 的 `py -3`。

## 4 算法与结果状态

| 算法标识 | 方法 | 是否保证最优 |
| --- | --- | --- |
| `greedy` | 按价值重量比排序，能放入就选择 | 不保证 |
| `dynamic_programming` | 容量倒序更新，保存决策并回溯 | 完成时保证 |
| `branch_and_bound` | 深度优先搜索，分数背包上界剪枝 | 完成时保证 |
| `brute_force` | 搜索选与不选分支，仅舍弃超重分支 | 完成时保证 |

- `optimal`：精确算法完成，已证明最优。
- `heuristic`：贪心得到的可行解，不代表已经证明最优。
- `timeout`：预算用完，返回目前已知可行解，不声称最优。
- `cancelled`：用户取消，可能返回空集或当前可行解。
- `skipped`：动态规划超过决策表单元上限，明确跳过并附贪心可行解。

`--time-limit` 是**每个算法**的合作式限时，不是硬实时保证。
检查间隔、排序、内存分配等会使实际耗时稍有超出。
全部四种算法的总等待时间可能接近单算法限时的四倍。
分支搜索的初始下界使用贪心解，但穷举算法不会使用价值上界剪枝。

动态规划采用有效容量 `min(C, 所有物品重量之和)`，默认最多分配
20,000,000 个 bytearray 决策单元，另有价值数组和 Python 对象开销。
包含完整选择方案回溯，因此**总空间为 O(nC)，不能称为 O(C)**。
等价值最优方案可能不唯一，各算法不保证选择同一组物品。

## 5 输入约定

容量为非负整数，重量为正整数，价值为非负整数，物品编号为唯一非空字符串。
允许空物品集、零容量、零价值、重复重量价值的不同物品；每个物品最多选择一次。
小数重量请先按统一单位缩放为整数，缩放会增加动态规划容量维度。

JSON：

```json
{
  "name": "example",
  "capacity": 10,
  "items": [
    {"id": "A", "weight": 2, "value": 6},
    {"id": "B", "weight": 4, "value": 8}
  ]
}
```

CSV 第一行必须为 `id,weight,value`，容量通过 `--capacity` 指定。

## 6 实验与复现

`results/reference/` 是报告使用的实测结果，不是手工填入的示例数据：

- `raw.csv`：165 次求解，含状态、价值、重量、操作次数、所选编号。
- `summary.csv` / `summary.json`：聚合统计。
- `instances.json`：50 个实验实例的全部物品，含随机种子。
- `metadata.json`：操作系统、Python版本、实验参数与计时范围。
- `n_runtime.svg` / `capacity_runtime.svg`：可直接用浏览器查看的实验曲线。

物品数实验固定容量120，n取8、12、16、20、24，各3个随机种子。
容量实验固定n=60，C取100、300、600、1200、2400，各3个随机种子，
同一种子在不同容量下使用相同物品。另有20组n=60、C=300的解质量实验。

同一实例的算法顺序按固定种子打乱，预热不计入结果。
运行时间取 `perf_counter_ns` 差值，包括排序、算法和回溯，不包括文件读写、
图表、界面和独立结果校验。规模统计使用3个不同实例的中位数，不是同一实例反复测量。
曲线只画正常完成运行的中位数；超时单列，不能把0.5秒当作完整求解时间。
最优基准仅来自已完成的精确算法；没有证明时质量比留空。

复现实验请输出到新目录，避免覆盖随报告交付的参考数据。
不同硬件、后台负载与Python版本的耗时会不同；限时搜索的中间可行解也可能不同。
本实验仅覆盖独立均匀随机数据，不能据此断言分支限界在所有分布上都优于动态规划。

## 7 项目结构

```text
main.py                    命令行入口及默认桌面启动
knapsack/models.py         数据模型与独立可行性校验
knapsack/algorithms.py     四种求解算法及合作式预算
knapsack/io.py             JSON/CSV与随机实例
knapsack/experiments.py    批量实验、统计和SVG曲线
knapsack/gui.py            Tk桌面界面及后台工作线程
tests/                     自动测试与小规模独立枚举核对
scripts/gui_smoke.py       可选图形桌面测试
data/                      两个可直接运行的输入示例
results/reference/         报告对应的实验原始数据
```

参考文档：Python标准库 `tkinter`、`unittest`、`time.perf_counter_ns`、`fractions.Fraction`。
