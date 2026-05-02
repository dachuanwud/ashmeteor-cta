# crypto_cta

## 环境配置
```
conda create -n crypto_cta python==3.8.19
conda activate crypto_cta
pip install -r requirements.txt
```

### 更新说明
2024-10-16

修改了年化利率的计算，过去计算结果不对，现在正确了

2024-10-25

最近亏麻了，妈的好难受，增加了个轮动脚本

初步完善了轮动脚本，收益让我不可置信！！！

2024-10-26

妈的，我以为真有这种爆炸策略，白开心了一场。原来是排序的时候实际上需要shift到下个持仓周期，不然就是未来数据

彻底完善了轮动CTA框架。有两个脚本5，结果其实差异并不是特别大，主要区别是回测收益计算方式不同

5_shift_equity脚本计算回测曲线是将资金曲线看成币价做成涨跌幅求平均后计算来的

5_shift_kline脚本计算回测曲线是将选币结果读入，然后根据币价涨跌幅重新计算资金曲线

增加了遍历shift轮动参数的脚本6，默认回测计算用的5_shift_kline

2024-10-28

完善了轮动脚本，增加了自动化功能，不必手动填来填去

2024-10-29

手续费计算有问题，完善了手续费计算，果然收益没有那么爆炸了


### 功能说明

#### 数据整理脚本
1_kline_data.py

#### 计算单次回测

#### 计算单次单参数回测
2_fast_backview.py
#### 计算pearson轮动单参数回测
2_fast_backview_pearson.py

#### 遍历参数
##### 多线程
3_fastover.py
##### 多进程
3_fastover_joblib.py

#### 绘制单参数平原或者双参数热力图
4_strategy_evaluate.py

### 推荐使用方式：统一入口

现在推荐只修改 `config.py`，然后固定执行统一入口：

```bash
cd /Users/houjl/Downloads/CTA回测/crypto_cta
python3 run_configured.py
```

常用配置项在 `config.py` 中：

```python
symbol_list = ['ETH-USDT']          # 回测币种
signal_name_list = ['dc_flash']     # 策略名，对应 factors/ 下的文件名
para = [290]                        # 单次回测参数
rule_type_list = ['1H']             # K线周期
date_start = '2021-01-01'           # 回测开始时间
date_end = '2026-01-01'             # 回测结束时间
```

`run_task_list` 控制统一入口执行什么任务：

```python
run_task_list = ['backtest']                  # 单次回测，使用 para
run_task_list = ['sweep']                     # 参数遍历，使用策略里的 para_list()
run_task_list = ['plot']                      # 根据已有参数遍历结果画参数平原/热力图
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

### 如何生成参数平原

参数平原不是直接用单次回测生成的，必须先有参数遍历结果。

推荐步骤：

1. 在策略文件里确认 `para_list()` 已配置好参数范围。例如单参数策略：

```python
def para_list():
    return [[10], [20], [30]]
```

2. 在 `config.py` 中配置策略、币种、周期和回测区间：

```python
symbol_list = ['ETH-USDT']
signal_name_list = ['dc_flash']
rule_type_list = ['1H']
date_start = '2021-01-01'
date_end = '2026-01-01'
```

3. 配置是否分区间看参数平原：

```python
per_eva = 'a'  # 全区间
```

可选值：

```text
a -> 全区间一起评估
y -> 按年分区间评估
m -> 按月分区间评估
w -> 按周分区间评估
```

如果要看年度参数稳定性：

```python
per_eva = 'y'
```

4. 配置任务为参数遍历加画图：

```python
run_task_list = ['sweep', 'plot']
```

5. 执行统一入口：

```bash
python3 run_configured.py
```

输出位置：

```text
data/output/para/      # 参数遍历 CSV
data/output/para_pic/  # 参数平原/热力图 HTML
```

单参数策略会生成参数平原图；双参数策略会生成热力图。更完整的使用说明见 `agent.md`。

### 如何生成策略调试可视化图

策略调试可视化用于查看：

- 该币种的 K 线价格曲线
- 成交量
- 策略轨道列，例如 `upper`、`lower`、`median`、`flash_stop_win`
- 买点、卖点和平仓触发点

在 `config.py` 中配置当前策略、币种、周期、参数和回测区间：

```python
symbol_list = ['ETH-USDT']
signal_name_list = ['dc_flash']
para = [290]
rule_type_list = ['1H']
date_start = '2021-01-01'
date_end = '2026-01-01'
run_task_list = ['visualize']
```

然后执行：

```bash
python3 run_configured.py
```

也可以直接执行底层脚本：

```bash
python3 5_strategy_visualize.py
```

输出位置：

```text
data/output/visualize/
```
