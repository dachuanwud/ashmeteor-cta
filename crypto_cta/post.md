# CTA策略回测框架使用说明

这是一个专门针对加密货币的CTA策略回测框架。框架支持多周期、多币种回测,支持参数遍历优化,并提供了详尽的回测评价指标和可视化分析工具。

## 主要特点

- 支持多币种、多周期回测
- 支持参数遍历优化
- 支持多进程并行计算
- 提供完整的回测评价指标
- 提供策略曲线可视化分析
- 支持止盈止损
- 考虑交易手续费和滑点
- 支持分段回测(按年、月、周)

## 环境配置

1. 创建虚拟环境:
```bash
conda create -n crypto_cta python==3.8.19
conda activate crypto_cta
```

2. 安装依赖:
```bash
pip install -r requirements.txt
```

## 配置说明

所有配置都在`config.py`中:

```python
# k线数据路径
data_center_path = 'D:/data/market/swap_1m'  # 原始1分钟k线数据路径
time_interval = '1m'    # k线数据周期

# 回测配置
symbol_list = ['1000PEPE-USDT']  # 回测币种列表
para = [180]  # 策略参数
proportion = 0.5  # 止盈止损比例
signal_name_list = ['sma']  # 策略名称列表
rule_type_list = ['1H']  # 回测周期列表
date_start = '2021-01-01'  # 回测开始时间
date_end = '2025-01-01'  # 回测结束时间
offset = 0  # 偏移量

# 交易成本
c_rate = 8/10000  # 手续费率
slippage = 1/1000  # 滑点率
leverage_rate = 1  # 杠杆倍数
min_margin_ratio = 1/100  # 最低保证金率

# 其他配置
drop_days = 10  # 币种上线初期不交易的天数
per_eva = 'a'  # 分段回测模式: y-按年, m-按月, w-按周, a-全部
del_mode = True  # 是否删除历史回测结果
cover_curve = False  # 是否绘制参数覆盖总资金曲线
```

## 使用流程

1. 数据准备
运行`1_kline_data.py`处理原始数据:
```bash
python 1_kline_data.py
```

2. 单次回测
运行`2_fast_backview.py`进行单次回测:
```bash 
python 2_fast_backview.py
```

3. 参数优化
运行`3_fastover.py`进行参数遍历优化:
```bash
python 3_fastover.py
```

4. 回测分析
运行`4_strategy_evaluate.py`生成回测分析报告:
```bash
python 4_strategy_evaluate.py
```

## 策略开发

1. 在`factors`目录下创建策略文件,例如`sma.py`

2. 策略文件需要实现两个函数:
- `signal()`: 计算交易信号
- `para_list()`: 定义参数遍历范围

示例:
```python
def signal(df, para=[200, 2], proportion=1, leverage_rate=1):
    """
    :param df: 原始数据
    :param para: 策略参数
    :return: 包含signal的DataFrame
    """
    # 计算信号...
    return df

def para_list():
    """
    :return: 参数遍历列表
    """
    return [[i] for i in range(20, 300, 20)]
```

## 输出说明

1. 回测结果保存在`data/output/para/`目录:
- `基准&{leverage_rate}&{rule_type}.csv`: 基准回测结果
- `{signal_name}&{symbol}&{leverage_rate}&{rule_type}.csv`: 策略回测结果

2. 资金曲线保存在`data/output/equity_curve/`目录

3. 可视化结果保存在`data/output/para_pic/`目录:
- 参数平原图(1维参数)
- 热力图(2维参数)

## 注意事项

1. 请确保原始数据路径配置正确

2. 建议先用小规模数据测试程序运行是否正常

3. 参数遍历时注意参数空间大小,避免占用过多资源

4. 可以通过调整`multiple_process`参数控制是否启用多进程

5. 回测结果包含详细的交易记录和统计指标,可用于策略分析优化

## 更新日志

2024-10-16
- 修正了年化收益率计算方法

2024-10-25/26
- 增加了轮动策略功能
- 完善了轮动CTA框架

2024-10-28
- 增加了自动化功能

2024-10-29  
- 修复了手续费计算问题

## 问题反馈

如有问题请提issue或联系开发者。

祝您使用愉快! 