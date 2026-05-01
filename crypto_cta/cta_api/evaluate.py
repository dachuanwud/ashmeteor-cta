import os
import ast
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objs as go
from plotly.offline import plot
from plotly.subplots import make_subplots
from config import root_path


def draw_chart_mat(df, draw_chart_list, pic_size=[9, 9], dpi=72, font_size=20, noise_pct=0.05, path=root_path+'/pic.pdf'):
    """
    绘制分布图
    :param df:  包含绘制指定分布数据的df
    :param draw_chart_list: 指定绘制的列
    :param pic_size:    指定画布大小
    :param dpi: 指定画布的dpi
    :param font_size:   指定字体大小
    :param noise_pct:   指定去除的异常值
    :return:
    """
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(num=1, figsize=(pic_size[0], pic_size[1]), dpi=dpi)
    plt.xticks(fontsize=font_size)
    plt.yticks(fontsize=font_size)
    row = len(draw_chart_list)
    count = 0
    for data in draw_chart_list:
        temp = df.copy()
        temp['Rank'] = temp[data].rank(pct=True)
        temp = temp[temp['Rank'] < (1 - noise_pct)]
        temp = temp[temp['Rank'] > noise_pct]
        # group = temp.groupby(data)
        # plt.hist(group.groups.keys(), 20)

        ax = plt.subplot2grid((row, 1), (count, 0))
        ax.hist(temp[data], 70)
        ax.set_xlabel(data)
        ax.set_ylabel('数量')
        count += 1

    # plt.show()
    plt.savefig(path)


def draw_equity_curve_mat(df, rtn, trade, title, path='./pic.html', show=True):
    """
    绘制附带K线的资金曲线
    :param df: 包含资金曲线列的df
    :param trade: 每笔交易
    :param title: 表名
    :param path: 保存路径
    :param show: 是否展示图片
    :return:
    """
    g = trade.copy()
    # 买卖点
    mark_point_list = []
    for i in g.index:
        buy_time = i
        sell_time = g.loc[i, 'end_bar']
        # 标记买卖点，在最高价上方标记
        y = df.loc[df['candle_begin_time'] == buy_time, 'high'].iloc[0] * 1.05
        mark_point_list.append({
            'x': buy_time,
            'y': y,
            'showarrow': True,
            'text': '开空' if g.loc[i, 'signal'] == -1 else '开多',
            'arrowside': 'end',
            'arrowhead': 7
        })
        y = df.loc[df['candle_begin_time'] == sell_time, 'low'].iloc[0] * 1.05
        mark_point_list.append({
            'x': sell_time,
            'y': y,
            'showarrow': True,
            'text': '平仓',
            'arrowside': 'end',
            'arrowhead': 7
        })
    trace1 = go.Candlestick(
        x=df['candle_begin_time'],
        open=df['open'],  # 字段数据必须是元组、列表、numpy数组、或者pandas的Series数据
        high=df['high'],
        low=df['low'],
        close=df['close']
    )

    trace2 = go.Scatter(x=df['candle_begin_time'], y=df['equity_curve'], name='资金曲线', yaxis='y2', line=dict(color='#4682B4'))
    layout = go.Layout(
        yaxis2=dict(anchor='x', overlaying='y', side='right'),  # 设置坐标轴的格式，一般次坐标轴在右侧
        xaxis_rangeslider=dict(visible=False),  # 隐藏范围滑块
        plot_bgcolor='white',  # 设置背景为白色
        updatemenus=[
            dict(
                buttons=[
                    dict(label="线性 y轴",
                         method="relayout",
                         args=[{"yaxis2.type": "linear"}]),  # 仅更改 yaxis2
                    dict(label="Log y轴",
                         method="relayout",
                         args=[{"yaxis2.type": "log"}]),  # 仅更改 yaxis2
                ],
                direction="down",
                showactive=True,
            )
        ]
    )
    fig = go.Figure(data=[trace1, trace2], layout=layout)

    fig.update_layout(template='none',width=1500,height=800,annotations=mark_point_list, title=title)

    plot(figure_or_data=fig, filename=path, auto_open=False)
    # 打开图片的html文件，需要判断系统的类型
    if show:
        res = os.system('start ' + path)
        if res != 0:
            os.system('open ' + path)

def draw_equity_curve_mat_V1(df, rtn, trade, title, path='./pic.html', show=True):
    """
    绘制附带K线的资金曲线
    :param df: 包含资金曲线列的df
    :param trade: 每笔交易
    :param title: 表名
    :param path: 保存路径
    :param show: 是否展示图片
    :return:
    """
    values = [[value] for value in rtn.T.iloc[:, 0].tolist()]

    g = trade.copy()
    # 买卖点
    mark_point_list = []
    for i in g.index:
        buy_time = i
        sell_time = g.loc[i, 'end_bar']
        # 标记买卖点，在最高价上方标记
        y = df.loc[df['candle_begin_time'] == buy_time, 'high'].iloc[0] * 1.05
        mark_point_list.append({
            'x': buy_time,
            'y': y,
            'showarrow': True,
            'text': '开空' if g.loc[i, 'signal'] == -1 else '开多',
            'arrowside': 'end',
            'arrowhead': 7
        })
        y = df.loc[df['candle_begin_time'] == sell_time, 'low'].iloc[0] * 1.05
        mark_point_list.append({
            'x': sell_time,
            'y': y,
            'showarrow': True,
            'text': '平仓',
            'arrowside': 'end',
            'arrowhead': 7
        })
    
    # 创建一个带有子图的图形
    fig = make_subplots(
        rows=3, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.02,
        specs=[[{"type": "table"}], 
               [{"type": "xy", "secondary_y": True}],
               [{"type": "xy"}]],
        row_heights=[0.1, 0.8, 0.1]
    )

    trace1 = go.Candlestick(
        x=df['candle_begin_time'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
    )

    trace2 = go.Scatter(
        x=df['candle_begin_time'], 
        y=df['equity_curve'], 
        name='资金曲线', 
        line=dict(color='#4682B4'),
    )

    trace3 = go.Bar(
        x=df['candle_begin_time'],
        y=df['volume'],
        name='成交量',
        marker=dict(color='rgba(158,202,225,0.5)')
    )

    # 添加轨迹到特定的子图
    fig.add_trace(
        go.Table(
            header=dict(values=list(rtn.columns),
                        fill_color='paleturquoise',
                        align='center'),
            cells=dict(values=values,
                       fill_color='lavender',
                       align='center'),
            columnwidth=[40]*len(rtn.columns)),
        row=1, col=1
    )
    fig.add_trace(trace1, secondary_y=False, row=2, col=1)
    fig.add_trace(trace2, secondary_y=True, row=2, col=1)
    fig.add_trace(trace3, row=3, col=1)

    fig.update_layout(
        template='none',
        hovermode='x',
        width=1650,
        height=950,
        annotations=mark_point_list,
        title=title,
        yaxis=dict(title='K线', side='left'),
        yaxis2=dict(title='资金曲线', anchor='x', overlaying='y', side='right'),
        yaxis3=dict(title='成交量'),
        xaxis_rangeslider=dict(visible=False),
        plot_bgcolor='white',
        updatemenus=[
            dict(
                buttons=[
                    dict(label="线性 y轴",
                         method="relayout",
                         args=[{"yaxis2.type": "linear"}]),
                    dict(label="Log y轴",
                         method="relayout",
                         args=[{"yaxis2.type": "log"}]),
                ],
                direction="down",
                showactive=True,
            )
        ]
    )

    fig.write_html(path, auto_open=False)

    # 打开图片的html文件，需要判断系统的类型
    if show:
        res = os.system('start ' + path)
        if res != 0:
            os.system('open ' + path)

def draw_pearson_curve(df, title, path='./pic.html', show=True):
    """
    绘制附带K线的资金曲线
    :param df: 包含资金曲线列的df
    :param trade: 每笔交易
    :param title: 表名
    :param path: 保存路径
    :param show: 是否展示图片
    :return:
    """

    trace2 = go.Scatter(x=df['candle_begin_time'], y=df['equity_curve'], name='资金曲线', yaxis='y2')
    layout = go.Layout(
        yaxis2=dict(anchor='x', overlaying='y', side='right')  # 设置坐标轴的格式，一般次坐标轴在右侧
    )
    fig = go.Figure(data=[trace2], layout=layout)

    fig.update_layout(title=title)

    plot(figure_or_data=fig, filename=path, auto_open=False)
    # 打开图片的html文件，需要判断系统的类型
    if show:
        res = os.system('start ' + path)
        if res != 0:
            os.system('open ' + path)

def draw_equity_parameters_plateau(df: pd.DataFrame, draw_chart_list, show=True, path='./pic.html'):
    """
    绘制参数平原
    :param df: 原数据
    :param show: 是否显示热力图
    :return:
    """
    df = df.copy()
    df.sort_values(['回测区间'], inplace=True, ascending=True)
    backtest_intervals = df['回测区间'].unique()

    # 计算三行布局所需的列数
    num_intervals = len(backtest_intervals)
    num_rows = 3
    num_cols = (num_intervals + num_rows - 1) // num_rows

    # 创建三行的子图网格
    fig = make_subplots(
        rows=num_rows, cols=num_cols,
        subplot_titles=backtest_intervals,
        shared_xaxes=False, 
        shared_yaxes=False, 
        vertical_spacing=0.1,
        horizontal_spacing=0.1
    )

    for i, interval in enumerate(backtest_intervals):
        # 确定行和列的位置
        row = (i % num_rows) + 1
        col = (i // num_rows) + 1

        # 过滤出当前回测区间的数据
        plateau_df = df[df['回测区间'] == interval].copy()
        plateau_df.sort_values(by=[draw_chart_list[0]], inplace=True)
        plateau_df.reset_index(inplace=True, drop=True)

        trace = go.Bar(
            x=plateau_df[draw_chart_list[0]],
            y=plateau_df[draw_chart_list[1]],
            name=interval,
            marker_color='#4682B4'
        )
        fig.add_trace(trace, row=row, col=col)

    # 设置图表的布局
    fig_height = 300 * num_rows  # 每行的高度
    fig_width = 800 * num_cols  # 每列的宽度

    fig.update_layout(
        height=fig_height, 
        width=fig_width,
        showlegend=False, 
        title_text='柱状图',
        plot_bgcolor='white',
        paper_bgcolor='white'
    )

    fig.write_html(path)

    # 打开HTML文件
    if show:
        res = os.system('start ' + path)
        if res != 0:
            os.system('open ' + path)


def draw_thermodynamic_diagram(df, draw_chart_list, show=True, path='./pic.pdf'):
    """
    绘制热力图
    :param df: 原数据
    :param show: 是否显示热力图
    :param path: 保存路径
    :return:
    """
    df = df.copy()
    # 提取 para 的 x 和 y 值，并将其转换为独立的列
    df['para_x'] = df[draw_chart_list[0]].apply(lambda x: eval(x)[0])
    df['para_y'] = df[draw_chart_list[0]].apply(lambda x: eval(x)[1])

    # 获取所有不同的回测区间
    backtest_intervals = sorted(df['回测区间'].unique())

    # 创建带有子图的图表
    fig = make_subplots(
        rows=1, cols=len(backtest_intervals),
        subplot_titles=backtest_intervals
    )

    for i, interval in enumerate(backtest_intervals):
        # 过滤出当前回测区间的数据
        hot_df = df[df['回测区间'] == interval]
        hot_df.sort_values(by=['para_x', 'para_y'], inplace=True)
        hot_df.reset_index(inplace=True, drop=True)

        heatmap = go.Heatmap(
            showlegend=True,
            name=interval,
            x=hot_df['para_x'],
            y=hot_df['para_y'],
            z=hot_df[draw_chart_list[1]],
            type='heatmap',
            colorbar=None
        )

        fig.add_trace(heatmap, row=1, col=i+1)

    # 计算图表的高度和宽度
    fig_height = 600  # 固定高度600px
    fig_width = 600 * len(backtest_intervals)  # 每个子图600px宽度

    fig.update_layout(
        height=fig_height,  # 固定高度
        width=fig_width,  # 根据子图数量调整宽度
        title_text="热力图",
        showlegend=False
    )

    fig.update_layout(margin=dict(t=100, r=150, b=100, l=100), autosize=True)

    # plot(figure_or_data=fig, filename=path, auto_open=False)
    fig.write_html(path)

    # 打开图片的html文件，需要判断系统的类型
    if show:
        res = os.system('start ' + path)
        if res != 0:
            os.system('open ' + path)

def draw_shift_parameters_plateau(df: pd.DataFrame, draw_chart_list, show=True, path='./pic.html'):
    """
    绘制参数平原
    :param df: 原数据
    :param show: 是否显示热力图
    :return:
    """
    df = df.copy()
    df.sort_values(['回测区间'], inplace=True, ascending=True)
    backtest_intervals = df['回测区间'].unique()

    # 计算三行布局所需的列数
    num_intervals = len(backtest_intervals)
    num_rows = 3
    num_cols = (num_intervals + num_rows - 1) // num_rows

    # 创建三行的子图网格
    fig = make_subplots(
        rows=num_rows, cols=num_cols,
        subplot_titles=backtest_intervals,
        shared_xaxes=False, 
        shared_yaxes=False, 
        vertical_spacing=0.1,
        horizontal_spacing=0.1
    )

    for i, interval in enumerate(backtest_intervals):
        # 确定行和列的位置
        row = (i % num_rows) + 1
        col = (i // num_rows) + 1

        # 过滤出当前回测区间的数据
        plateau_df = df[df['回测区间'] == interval].copy()
        plateau_df[draw_chart_list[0]] = plateau_df[draw_chart_list[0]].apply(lambda x:ast.literal_eval(x))
        plateau_df[draw_chart_list[0]] = plateau_df[draw_chart_list[0]].apply(lambda x:x[0])
        plateau_df.sort_values(by=[draw_chart_list[0]], inplace=True)
        plateau_df.reset_index(inplace=True, drop=True)

        trace = go.Bar(
            x=plateau_df[draw_chart_list[0]],
            y=plateau_df[draw_chart_list[1]],
            name=interval,
            marker_color='#4682B4'
        )
        fig.add_trace(trace, row=row, col=col)

    # 设置图表的布局
    fig_height = 300 * num_rows  # 每行的高度
    fig_width = 800 * num_cols  # 每列的宽度

    fig.update_layout(
        height=fig_height, 
        width=fig_width,
        showlegend=False, 
        title_text='柱状图',
        plot_bgcolor='white',
        paper_bgcolor='white'
    )

    fig.write_html(path)

    # 打开HTML文件
    if show:
        res = os.system('start ' + path)
        if res != 0:
            os.system('open ' + path)

def draw_equity_curve_plotly(df, data_dict, date_col=None, right_axis=None, pic_size=[1500, 800], chg=False,
                             title=None, path=root_path + '/data/pic.html', show=True):
    """
    绘制策略曲线
    :param df: 包含净值数据的df
    :param data_dict: 要展示的数据字典格式：｛图片上显示的名字:df中的列名｝
    :param date_col: 时间列的名字，如果为None将用索引作为时间列
    :param right_axis: 右轴数据 ｛图片上显示的名字:df中的列名｝
    :param pic_size: 图片的尺寸
    :param chg: datadict中的数据是否为涨跌幅，True表示涨跌幅，False表示净值
    :param title: 标题
    :param path: 图片路径
    :param show: 是否打开图片
    :return:
    """
    draw_df = df.copy()

    # 设置时间序列
    if date_col:
        time_data = draw_df[date_col]
    else:
        time_data = draw_df.index

    # 绘制左轴数据
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for key in data_dict:
        if chg:
            draw_df[data_dict[key]] = (draw_df[data_dict[key]] + 1).fillna(1).cumprod()
        fig.add_trace(go.Scatter(x=time_data, y=draw_df[data_dict[key]], name=key, ))

    # 绘制右轴数据
    if right_axis:
        key = list(right_axis.keys())[0]
        fig.add_trace(go.Scatter(x=time_data, y=draw_df[right_axis[key]], name=key + '(右轴)',
                                 #  marker=dict(color='rgba(220, 220, 220, 0.8)'),
                                 marker_color='orange',
                                 opacity=0.1, line=dict(width=0),
                                 fill='tozeroy',
                                 yaxis='y2'))  # 标明设置一个不同于trace1的一个坐标轴
        for key in list(right_axis.keys())[1:]:
            fig.add_trace(go.Scatter(x=time_data, y=draw_df[right_axis[key]], name=key + '(右轴)',
                                     #  marker=dict(color='rgba(220, 220, 220, 0.8)'),
                                     opacity=0.1, line=dict(width=0),
                                     fill='tozeroy',
                                     yaxis='y2'))  # 标明设置一个不同于trace1的一个坐标轴

    fig.update_layout(template="none", width=pic_size[0], height=pic_size[1], title_text=title,
                      hovermode="x unified", hoverlabel=dict(bgcolor='rgba(255,255,255,0.5)', ),
                      )
    fig.update_layout(
        updatemenus=[
            dict(
                buttons=[
                    dict(label="线性 y轴",
                         method="relayout",
                         args=[{"yaxis.type": "linear"}]),
                    dict(label="Log y轴",
                         method="relayout",
                         args=[{"yaxis.type": "log"}]),
                ])],
    )
    plot(figure_or_data=fig, filename=path, auto_open=False)

    fig.update_yaxes(
        showspikes=True, spikemode='across', spikesnap='cursor', spikedash='solid', spikethickness=1,  # 峰线
    )
    fig.update_xaxes(
        showspikes=True, spikemode='across+marker', spikesnap='cursor', spikedash='solid', spikethickness=1,  # 峰线
    )

    # 打开图片的html文件，需要判断系统的类型
    if show:
        res = os.system('start ' + path)
        if res != 0:
            os.system('open ' + path)

def draw_shift_equity_curve_plotly(df, data_dict, date_col=None, right_axis=None, pic_size=[1500, 800], chg=False,
                                   title=None, path='pic.html', show=True):
    draw_df = df.copy()

    # 设置时间序列
    if date_col:
        time_data = draw_df[date_col]
    else:
        time_data = draw_df.index

    # 初始化图形
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 定义颜色列表
    colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown']
    
    # 获取所有唯一的 equity_name
    draw_df['equity_name'] = draw_df['equity_name'].astype(str)
    unique_equity_names = draw_df['equity_name'].unique()
    
    # 创建一个字典，将每个 equity_name 映射到一个颜色
    color_map = {name: colors[i % len(colors)] for i, name in enumerate(unique_equity_names)}

    # 绘制左轴数据
    for key in data_dict:
        if chg:
            draw_df[data_dict[key]] = (draw_df[data_dict[key]] + 1).fillna(1).cumprod()

        # 分段绘制
        segments = []
        start_idx = 0
        for i in range(1, len(draw_df)):
            if draw_df['equity_name'].iloc[i] != draw_df['equity_name'].iloc[start_idx]:
                segments.append((start_idx, i))
                start_idx = i
        segments.append((start_idx, len(draw_df)))

        for start, end in segments:
            equity_name = draw_df['equity_name'].iloc[start]
            fig.add_trace(go.Scatter(
                x=time_data[start:end],
                y=draw_df[data_dict[key]].iloc[start:end],
                name=f"{key} ({equity_name})",
                line=dict(color=color_map[equity_name])
            ))

    # 绘制右轴数据
    if right_axis:
        for key in right_axis:
            fig.add_trace(go.Scatter(
                x=time_data,
                y=draw_df[right_axis[key]],
                name=key + '(右轴)',
                marker_color='orange',
                opacity=0.1,
                line=dict(width=0),
                fill='tozeroy',
                yaxis='y2'
            ))

    # 更新布局
    fig.update_layout(
        template="none",
        width=pic_size[0],
        height=pic_size[1],
        title_text=title,
        hovermode="x unified",
        hoverlabel=dict(bgcolor='rgba(255,255,255,0.5)')
    )

    # 添加按钮
    fig.update_layout(
        updatemenus=[
            dict(
                buttons=[
                    dict(label="线性 y轴",
                         method="relayout",
                         args=[{"yaxis.type": "linear"}]),
                    dict(label="Log y轴",
                         method="relayout",
                         args=[{"yaxis.type": "log"}]),
                ]
            )
        ]
    )

    # 绘制图形
    plot(figure_or_data=fig, filename=path, auto_open=False)

    # 更新轴
    fig.update_yaxes(showspikes=True, spikemode='across', spikesnap='cursor', spikedash='solid', spikethickness=1)
    fig.update_xaxes(showspikes=True, spikemode='across+marker', spikesnap='cursor', spikedash='solid', spikethickness=1)

    # 打开图片的html文件
    if show:
        res = os.system('start ' + path)
        if res != 0:
            os.system('open ' + path)