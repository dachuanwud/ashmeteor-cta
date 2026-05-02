import os

import pandas as pd
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from cta_api.position import position_for_future


OVERLAY_COLUMN_ORDER = [
    "upper",
    "lower",
    "median",
    "flash_stop_win",
    "up",
    "dn",
    "upper_boll",
    "lower_boll",
    "upper_atr",
    "lower_atr",
]


OVERLAY_STYLES = {
    "upper": dict(color="#d62728", width=1.2),
    "lower": dict(color="#2ca02c", width=1.2),
    "median": dict(color="#7f7f7f", width=1.1, dash="dot"),
    "flash_stop_win": dict(color="#ff7f0e", width=1.2, dash="dash"),
    "up": dict(color="#d62728", width=1.0, dash="dot"),
    "dn": dict(color="#2ca02c", width=1.0, dash="dot"),
    "upper_boll": dict(color="#9467bd", width=0.9, dash="dash"),
    "lower_boll": dict(color="#9467bd", width=0.9, dash="dash"),
    "upper_atr": dict(color="#8c564b", width=0.9, dash="dash"),
    "lower_atr": dict(color="#8c564b", width=0.9, dash="dash"),
}


MARKER_STYLE = {
    "开多": dict(symbol="triangle-up", color="#13a10e", y_col="high", y_mult=1.006),
    "开空": dict(symbol="triangle-down", color="#d13438", y_col="low", y_mult=0.994),
    "平仓": dict(symbol="x", color="#605e5c", y_col="close", y_mult=1.0),
}


def select_overlay_columns(df):
    return [col for col in OVERLAY_COLUMN_ORDER if col in df.columns]


def build_signal_markers(df):
    signal = df["signal"]
    marker_frames = {
        "开多": df[signal == 1].copy(),
        "开空": df[signal == -1].copy(),
        "平仓": df[signal == 0].copy(),
    }

    for name, marker_df in marker_frames.items():
        style = MARKER_STYLE[name]
        if marker_df.empty:
            marker_df["y"] = []
            continue
        marker_df["y"] = marker_df[style["y_col"]] * style["y_mult"]
    return marker_frames


def build_strategy_dataframe(config, signal_name, symbol, rule_type, para):
    df = pd.read_feather(os.path.join(config.data_path, rule_type, symbol + ".pkl"))
    df = df[df["offset"] == config.offset].copy()

    cls = __import__("factors.%s" % signal_name, fromlist=("",))
    df = cls.signal(df, para=para, proportion=config.proportion, leverage_rate=config.leverage_rate)
    df = position_for_future(df)
    df = df[
        (df["candle_begin_time"] >= pd.to_datetime(config.date_start))
        & (df["candle_begin_time"] <= pd.to_datetime(config.date_end))
    ].copy()
    df.reset_index(drop=True, inplace=True)
    return df


def draw_strategy_visualization(df, signal_name, symbol, rule_type, para, path, show=False):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.82, 0.18],
        specs=[[{"type": "xy"}], [{"type": "xy"}]],
    )

    fig.add_trace(
        go.Candlestick(
            x=df["candle_begin_time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="K线",
        ),
        row=1,
        col=1,
    )

    for col in select_overlay_columns(df):
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df[col],
                mode="lines",
                name=col,
                line=OVERLAY_STYLES.get(col, dict(width=1)),
            ),
            row=1,
            col=1,
        )

    for name, marker_df in build_signal_markers(df).items():
        if marker_df.empty:
            continue
        style = MARKER_STYLE[name]
        fig.add_trace(
            go.Scatter(
                x=marker_df["candle_begin_time"],
                y=marker_df["y"],
                mode="markers",
                name=name,
                marker=dict(symbol=style["symbol"], color=style["color"], size=10, line=dict(width=1, color="white")),
                customdata=marker_df[["signal", "pos"]].to_numpy() if "pos" in marker_df.columns else marker_df[["signal"]].to_numpy(),
                hovertemplate="%{x}<br>%{fullData.name}<br>price=%{y:.4f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Bar(
            x=df["candle_begin_time"],
            y=df["volume"],
            name="成交量",
            marker=dict(color="rgba(70,130,180,0.35)"),
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        template="none",
        hovermode="x unified",
        width=1700,
        height=950,
        title=f"{symbol}_{signal_name}_{para}_{rule_type}_visualize",
        plot_bgcolor="white",
        xaxis_rangeslider=dict(visible=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_yaxes(title_text="价格/策略轨道", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    fig.write_html(path, auto_open=False)

    if show:
        res = os.system("start " + path)
        if res != 0:
            os.system("open " + path)


def visualize_configured_strategy(config):
    output_dir = os.path.join(config.root_path, "data/output/visualize")
    os.makedirs(output_dir, exist_ok=True)

    output_paths = []
    for signal_name in config.signal_name_list:
        for symbol in config.symbol_list:
            for rule_type in config.rule_type_list:
                df = build_strategy_dataframe(config, signal_name, symbol, rule_type, config.para)
                filename = f"{symbol}_{signal_name}_{config.para}_{rule_type}.html"
                path = os.path.join(output_dir, filename)
                draw_strategy_visualization(
                    df=df,
                    signal_name=signal_name,
                    symbol=symbol,
                    rule_type=rule_type,
                    para=config.para,
                    path=path,
                    show=getattr(config, "visualize_show", False),
                )
                output_paths.append(path)
                print(f"策略可视化已生成: {path}")
    return output_paths
