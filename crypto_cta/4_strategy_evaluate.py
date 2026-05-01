import glob
import inspect

import numpy as np
from cta_api.tools import get_list_dimension
from config import *
from cta_api.evaluate import *
from cta_api.function import write_file, num_to_pct

pd.set_option('expand_frame_repr', False)  # 当列太多时不换行

# 遍历所有策略结果
for signal_name in signal_name_list:
    cls = __import__('factors.%s' % signal_name, fromlist=('',))
    para_list = cls.para_list()
    dim = get_list_dimension(para_list)
    for symbol in symbol_list:
        for rule_type in rule_type_list:
            # === 获取所有指定策略的遍历结果
            path = os.path.join(root_path, f'data/output/para/{signal_name}&{symbol}&{leverage_rate}&{rule_type}.csv')  # python自带的库，或者某文件夹中所有csv文件的路径
            # 读取最优参数，选择排名前strategy_num的
            try:
                df = pd.read_csv(path, encoding='gbk')
            except FileNotFoundError:
                print(f"File not found: {path}")
                continue
            
            df.replace(np.inf, -1, inplace=True)
            # df = df.sort_values(by='年化收益/回撤比', ascending=False).head(1)
            df['strategy_name'] = path.split('/')[-1].split('&')[0]
            filename = path.split('/')[-1][:-4]
            df['symbol'] = filename.split('&')[1]
            df['leverage'] = filename.split('&')[2]
            df['周期'] = filename.split('&')[3]

            # 合并所有币种的遍历结果
            rtn = df
            rtn.reset_index(inplace=True, drop=False)
            # === 对一些列进行处理
            rtn['最大回撤'] = rtn['最大回撤'].apply(lambda x: float(x[:-1]) / 100)
            rtn['币种原始最大回撤'] = rtn['币种原始最大回撤'].apply(lambda x: float(x[:-1]) / 100)
            rtn['年化收益'] = rtn['年化收益'].apply(lambda x: float(x))
            rtn['币种原始年化收益'] = rtn['币种原始年化收益'].apply(lambda x: float(x))

            # 把合并的数据根据年化收益回撤比排序
            rtn.sort_values('年化收益/回撤比', inplace=True, ascending=False)

            rtn['年化收益/回撤比_超额'] = rtn['年化收益/回撤比'] - rtn['币种原始年化收益/回撤比']
            all_symbol_rtn = rtn[['strategy_name', 'symbol', '周期', 'leverage', 'para', '累积净值', '年化收益', '最大回撤', '年化收益/回撤比','年化收益/回撤比_超额','回测区间']]
            print(all_symbol_rtn)
            draw_chart_list = ['para', '累积净值']
            print('参数维数为:',dim)
            if os.path.exists(os.path.join(root_path,f'data/output/para_pic')) == False:
                os.makedirs(os.path.join(root_path,f'data/output/para_pic'))
            if dim == 1:
                if not all_symbol_rtn.empty:
                    print('绘制参数平原')
                    draw_equity_parameters_plateau(all_symbol_rtn,draw_chart_list,show=False,path=os.path.join(root_path,f'data/output/para_pic/{signal_name}_{symbol}_{rule_type}_{per_eva}.html'))

            if dim == 2:
                if not all_symbol_rtn.empty:
                    draw_thermodynamic_diagram(all_symbol_rtn,draw_chart_list,show=False,path=os.path.join(root_path,f'data/output/para_pic/{signal_name}_{symbol}_{rule_type}_{per_eva}.html'))
