# CTA 回测系统使用说明

本工程推荐使用“只改配置 + 固定入口”的方式运行回测。不要为了每个策略单独写脚本；策略、标的、周期、参数和执行任务都应优先通过 `config.py` 配置。

## 统一入口

固定从工程根目录执行：

```bash
cd /Users/houjl/Downloads/CTA回测/crypto_cta
python3 run_configured.py
```

`run_configured.py` 会读取 `config.py` 中的配置，并按 `run_task_list` 指定的任务顺序调用底层脚本。

## 核心配置文件

主要修改：

```text
/Users/houjl/Downloads/CTA回测/crypto_cta/config.py
```

常用配置项：

```python
symbol_list = ['ETH-USDT']          # 回测币种
signal_name_list = ['dc_flash']     # 策略名，对应 factors/ 下的文件名
para = [290]                        # 单次回测参数
rule_type_list = ['1H']             # K线周期
date_start = '2021-01-01'           # 回测开始时间
date_end = '2026-01-01'             # 回测结束时间
```

策略名就是 `factors/` 目录里的 Python 文件名，例如：

```python
signal_name_list = ['adapt_bolling']
signal_name_list = ['dc_flash']
```

## 执行任务配置

`config.py` 中使用 `run_task_list` 控制统一入口要执行的任务：

```python
run_task_list = ['backtest']
```

可选任务：

```python
run_task_list = ['backtest']                  # 单次回测，使用 para
run_task_list = ['sweep']                     # 参数遍历，使用策略里的 para_list()
run_task_list = ['plot']                      # 根据参数遍历结果画参数平原/热力图
run_task_list = ['visualize']                 # 生成策略调试可视化图
run_task_list = ['sweep', 'plot']             # 先参数遍历，再画参数平原/热力图
run_task_list = ['sweep', 'plot', 'backtest'] # 参数遍历、画图、再按 para 单次回测
```

底层对应关系：

```text
backtest -> 2_fast_backview.py
sweep    -> 3_fastover.py
plot     -> 4_strategy_evaluate.py
visualize -> 5_strategy_visualize.py
```

## 参数遍历分区

`config.py` 中使用 `per_eva` 控制参数遍历和参数图的分区方式：

```python
per_eva = 'a'
```

含义：

```text
a -> 全区间一起评估
y -> 按年分区间评估
m -> 按月分区间评估
w -> 按周分区间评估
```

例如要看年度参数稳定性：

```python
per_eva = 'y'
run_task_list = ['sweep', 'plot']
```

然后执行：

```bash
python3 run_configured.py
```

## 输出目录

单次回测资金曲线：

```text
data/output/pic/
data/output/equity_curve/
```

参数遍历结果：

```text
data/output/para/
```

参数平原/热力图：

```text
data/output/para_pic/
```

策略调试可视化图：

```text
data/output/visualize/
```

## 策略调试可视化

当需要查看某个币种的价格曲线、策略上轨/下轨/中轨，以及买点、卖点、触发点时，使用：

```python
run_task_list = ['visualize']
```

然后执行：

```bash
python3 run_configured.py
```

也可以直接运行底层脚本：

```bash
python3 5_strategy_visualize.py
```

可视化图会读取当前 `config.py` 中的：

```python
symbol_list
signal_name_list
para
rule_type_list
date_start
date_end
```

输出 HTML 到：

```text
data/output/visualize/
```

图中会包含：

- K线价格曲线
- 成交量
- 策略轨道列，例如 `upper`、`lower`、`median`、`flash_stop_win`
- `signal = 1` 的开多点
- `signal = -1` 的开空点
- `signal = 0` 的平仓点

## 新增策略接入方式

在 `factors/` 下新增策略文件，例如：

```text
factors/my_strategy.py
```

策略文件至少提供两个函数：

```python
def signal(df, para, proportion, leverage_rate):
    # 生成 signal 列
    return df


def para_list():
    return [[10], [20], [30]]
```

然后在 `config.py` 中配置：

```python
signal_name_list = ['my_strategy']
```

即可通过统一入口运行：

```bash
python3 run_configured.py
```

## 当前示例配置

当前配置示例为 ETH 的闪电侠策略：

```python
symbol_list = ['ETH-USDT']
signal_name_list = ['dc_flash']
para = [290]
rule_type_list = ['1H']
date_start = '2021-01-01'
date_end = '2026-01-01'
run_task_list = ['backtest']
```

直接执行：

```bash
python3 run_configured.py
```

即运行 ETH 的 `dc_flash` 单次回测。

## 使用原则

- 优先修改 `config.py`，不要为每个策略额外写一次性脚本。
- 单次回测使用 `para`。
- 参数遍历使用策略文件中的 `para_list()`。
- 参数图依赖参数遍历结果，通常先执行 `sweep` 再执行 `plot`。
- 新增策略时，保持 `signal(df, para, proportion, leverage_rate)` 和 `para_list()` 这两个接口一致。
