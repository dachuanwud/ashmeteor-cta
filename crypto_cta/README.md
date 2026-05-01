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