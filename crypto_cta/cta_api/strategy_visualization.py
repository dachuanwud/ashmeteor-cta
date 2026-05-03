import os
import ast
import html

import pandas as pd
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from cta_api.function import cal_equity_curve
from cta_api.position import position_for_future
from cta_api.statistics import transfer_equity_curve_to_trade, strategy_evaluate


OVERLAY_COLUMN_ORDER = [
    "upper",
    "lower",
    "median",
    "median_fast",
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
    "median_fast": dict(color="#245f9f", width=1.0, dash="dash"),
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
    "止损平仓": dict(symbol="diamond-x", color="#f28c28", y_col="close", y_mult=1.0, size=13),
    "追单过滤": dict(symbol="square", color="#7a3db8", y_col="close", y_mult=1.0, size=12),
}


PAGE_CSS = """
:root {
  --bg: #f4f1ea;
  --ink: #161616;
  --muted: #6d675f;
  --line: #d8d0c2;
  --panel: #fffaf1;
  --panel-strong: #f7ead5;
  --green: #1f8a5b;
  --red: #c64a3a;
  --blue: #245f9f;
  --gold: #9b6b1b;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: ui-serif, Georgia, "Times New Roman", "Songti SC", serif;
}
.page {
  width: min(1760px, calc(100vw - 48px));
  margin: 0 auto;
  padding: 28px 0 36px;
}
.topbar {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 20px;
  align-items: end;
  border-bottom: 1px solid var(--line);
  padding-bottom: 18px;
  margin-bottom: 18px;
}
h1 {
  margin: 0 0 6px;
  font-size: clamp(22px, 4vw, 30px);
  line-height: 1.05;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}
.subtitle {
  color: var(--muted);
  font-size: 14px;
  overflow-wrap: anywhere;
}
.stamp {
  border: 1px solid var(--line);
  background: var(--panel);
  padding: 10px 12px;
  font-size: 12px;
  color: var(--muted);
  text-align: right;
}
.cards {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0;
}
.card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px 12px 10px;
  min-height: 78px;
}
.label {
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 8px;
}
.value {
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
}
.value.good { color: var(--green); }
.value.bad { color: var(--red); }
.section {
  margin-top: 14px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
}
.section-title {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
  padding: 12px 14px;
  background: var(--panel-strong);
  border-bottom: 1px solid var(--line);
  font-size: 14px;
  font-weight: 700;
}
.section-note {
  color: var(--muted);
  font-size: 12px;
  font-weight: 400;
  white-space: normal;
}
.chart-wrap {
  background: #ffffff;
  overflow: hidden;
}
.chart-wrap .js-plotly-plot,
.chart-wrap .plotly-graph-div {
  width: 100% !important;
}
.comparison-wrap {
  background: #ffffff;
  border-bottom: 1px solid var(--line);
}
.comparison-wrap .js-plotly-plot,
.comparison-wrap .plotly-graph-div {
  width: 100% !important;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th, td {
  border-bottom: 1px solid var(--line);
  padding: 9px 10px;
  text-align: right;
  white-space: nowrap;
}
th:first-child, td:first-child { text-align: left; }
tr.selected { background: #f5dec0; }
tr:last-child td { border-bottom: 0; }
.grid-2 {
  display: grid;
  grid-template-columns: 0.9fr 1.1fr;
  gap: 14px;
}
@media (max-width: 1100px) {
  .page { width: calc(100vw - 24px); }
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid-2 { grid-template-columns: 1fr; }
  .topbar { grid-template-columns: 1fr; }
  .stamp { text-align: left; }
}
"""


def select_overlay_columns(df):
    return [col for col in OVERLAY_COLUMN_ORDER if col in df.columns]


def build_signal_markers(df):
    signal = df["signal"]
    stop_loss_trigger = df.get("stop_loss_trigger", False)
    if not isinstance(stop_loss_trigger, pd.Series):
        stop_loss_trigger = pd.Series(False, index=df.index)
    anti_chase_trigger = df.get("anti_chase_block_trigger", False)
    if not isinstance(anti_chase_trigger, pd.Series):
        anti_chase_trigger = pd.Series(False, index=df.index)
    close_signal = signal == 0
    marker_frames = {
        "开多": df[signal == 1].copy(),
        "开空": df[signal == -1].copy(),
        "平仓": df[
            close_signal
            & ~stop_loss_trigger
            & ~anti_chase_trigger
        ].copy(),
        "止损平仓": df[close_signal & stop_loss_trigger].copy(),
        "追单过滤": df[close_signal & anti_chase_trigger].copy(),
    }

    for name, marker_df in marker_frames.items():
        style = MARKER_STYLE[name]
        if marker_df.empty:
            marker_df["y"] = []
            continue
        marker_df["y"] = marker_df[style["y_col"]] * style["y_mult"]
    return marker_frames


def _parse_parameter(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        parsed = ast.literal_eval(str(value))
        if isinstance(parsed, (list, tuple)):
            return list(parsed)
    except (ValueError, SyntaxError):
        pass
    return [value]


def _same_parameter(left, right):
    return _parse_parameter(left) == _parse_parameter(right)


def _fmt(value):
    if pd.isna(value):
        return "-"
    return str(value)


def _pct(value):
    if pd.isna(value):
        return "-"
    return f"{value:.2%}"


def add_equity_diagnostics(df):
    result = df.copy()
    result["equity_peak"] = result["equity_curve"].cummax()
    result["drawdown"] = result["equity_curve"] / result["equity_peak"] - 1
    result["benchmark_equity"] = result["close"] / result["close"].iloc[0]
    result["benchmark_peak"] = result["benchmark_equity"].cummax()
    result["benchmark_drawdown"] = result["benchmark_equity"] / result["benchmark_peak"] - 1
    return result


def build_parameter_rank_summary(parameter_df, selected_para, top_n=10):
    if parameter_df is None or parameter_df.empty:
        return []

    ranked = parameter_df.copy()
    ranked = ranked.sort_values("年化收益/回撤比", ascending=False).head(top_n)
    rows = []
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        rows.append(
            {
                "rank": rank,
                "parameter": row["para"],
                "cum_value": row["累积净值"],
                "annual_return": row["年化收益"],
                "max_drawdown": row["最大回撤"],
                "return_drawdown": row["年化收益/回撤比"],
                "selected": _same_parameter(row["para"], selected_para),
            }
        )
    return rows


def select_comparison_parameters(parameter_df, current_para, limit=4):
    selected = [_parse_parameter(current_para)]
    if parameter_df is None or parameter_df.empty or limit <= 1:
        return selected[:limit]

    ranked = parameter_df.sort_values("年化收益/回撤比", ascending=False)
    for _, row in ranked.iterrows():
        candidate = _parse_parameter(row["para"])
        if candidate in selected:
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected


def build_comparison_summary(analyses, current_para):
    rows = []
    for analysis in analyses:
        values = analysis["metrics"].iloc[:, 0]
        parameter = analysis["para"]
        trade_count = len(analysis.get("trade", []))
        rows.append(
            {
                "parameter": str(parameter),
                "cum_value": _fmt(values.get("累积净值")),
                "annual_return": _fmt(values.get("年化收益")),
                "max_drawdown": _fmt(values.get("最大回撤")),
                "return_drawdown": _fmt(values.get("年化收益/回撤比")),
                "win_rate": _fmt(values.get("胜率")),
                "trade_count": trade_count,
                "avg_holding": _fmt(values.get("平均持仓周期")),
                "selected": _same_parameter(parameter, current_para),
            }
        )
    rows.sort(key=lambda row: not row["selected"])
    return rows


def load_parameter_result(config, signal_name, symbol, rule_type):
    path = os.path.join(
        config.root_path,
        f"data/output/para/{signal_name}&{symbol}&{config.leverage_rate}&{rule_type}.csv",
    )
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, encoding="gbk")


def build_strategy_analysis(config, signal_name, symbol, rule_type, para):
    df = build_strategy_dataframe(config, signal_name, symbol, rule_type, para)
    min_amount = config.min_amount_dict[symbol]
    df = cal_equity_curve(
        df,
        slippage=config.slippage,
        c_rate=config.c_rate,
        leverage_rate=config.leverage_rate,
        min_amount=min_amount,
        min_margin_ratio=config.min_margin_ratio,
    )
    df = add_equity_diagnostics(df)
    trade = transfer_equity_curve_to_trade(df)
    eval_trade = trade.copy()
    metrics, monthly_return = strategy_evaluate(df.copy(), eval_trade, rule_type)
    parameter_df = load_parameter_result(config, signal_name, symbol, rule_type)
    parameter_rows = build_parameter_rank_summary(parameter_df, para)
    yearly_return = (
        df.set_index("candle_begin_time")["equity_change"]
        .resample("YE")
        .apply(lambda x: (1 + x).prod() - 1)
        .reset_index()
    )
    yearly_return["year"] = yearly_return["candle_begin_time"].dt.year.astype(str)
    return {
        "para": para,
        "df": df,
        "trade": eval_trade,
        "metrics": metrics,
        "monthly_return": monthly_return,
        "parameter_rows": parameter_rows,
        "yearly_return": yearly_return,
    }


def build_comparison_analyses(config, signal_name, symbol, rule_type, current_para, parameter_df):
    comparison_parameters = select_comparison_parameters(parameter_df, current_para, limit=4)
    analyses = []
    for parameter in comparison_parameters:
        analyses.append(build_strategy_analysis(config, signal_name, symbol, rule_type, parameter))
    return analyses


def build_metric_cards(metrics, para, trade=None):
    values = metrics.iloc[:, 0]
    trade_count = len(trade) if trade is not None else int(values.get("盈利笔数", 0)) + int(values.get("亏损笔数", 0))
    cards = [
        ("参数", str(para), ""),
        ("累积净值", _fmt(values.get("累积净值")), "good"),
        ("年化收益", _fmt(values.get("年化收益")), "good"),
        ("最大回撤", _fmt(values.get("最大回撤")), "bad"),
        ("年化收益/回撤比", _fmt(values.get("年化收益/回撤比")), ""),
        ("胜率", _fmt(values.get("胜率")), ""),
        ("开仓次数", str(trade_count), ""),
        ("平均持仓", _fmt(values.get("平均持仓周期")), ""),
    ]
    return cards


def render_metric_cards(cards):
    return "\n".join(
        f'<div class="card"><div class="label">{html.escape(label)}</div>'
        f'<div class="value {klass}">{html.escape(value)}</div></div>'
        for label, value, klass in cards
    )


def render_parameter_table(rows):
    if not rows:
        return '<div class="section-note" style="padding:12px 14px;">未找到参数遍历 CSV，暂不显示参数排名。</div>'
    body = []
    for row in rows:
        selected = " selected" if row["selected"] else ""
        body.append(
            f'<tr class="{selected}">'
            f'<td>{row["rank"]}</td>'
            f'<td>{html.escape(str(row["parameter"]))}</td>'
            f'<td>{html.escape(str(row["cum_value"]))}</td>'
            f'<td>{html.escape(str(row["annual_return"]))}</td>'
            f'<td>{html.escape(str(row["max_drawdown"]))}</td>'
            f'<td>{html.escape(str(row["return_drawdown"]))}</td>'
            "</tr>"
        )
    return (
        "<table><thead><tr><th>排名</th><th>参数</th><th>累积净值</th><th>年化收益</th>"
        "<th>最大回撤</th><th>年化/回撤</th></tr></thead><tbody>"
        + "\n".join(body)
        + "</tbody></table>"
    )


def render_trade_table(trade, top_n=16):
    if trade.empty:
        return '<div class="section-note" style="padding:12px 14px;">当前参数没有形成交易记录。</div>'
    display = trade.copy()
    display["start_time"] = display.index
    display["方向"] = display["signal"].map({1: "多", -1: "空"}).fillna(display["signal"].astype(str))
    display["收益"] = display["change"].map(_pct)
    display = display.sort_values("change", ascending=True).head(top_n)
    body = []
    for _, row in display.iterrows():
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row['start_time']))}</td>"
            f"<td>{html.escape(str(row['end_bar']))}</td>"
            f"<td>{html.escape(str(row['方向']))}</td>"
            f"<td>{int(row['bar_num'])}</td>"
            f"<td>{html.escape(str(row['收益']))}</td>"
            f"<td>{html.escape(str(round(row['end_equity_curve'], 4)))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>开仓时间</th><th>平仓时间</th><th>方向</th><th>K线数</th>"
        "<th>单笔收益</th><th>平仓净值</th></tr></thead><tbody>"
        + "\n".join(body)
        + "</tbody></table>"
    )


def render_yearly_table(yearly_return):
    if yearly_return.empty:
        return '<div class="section-note" style="padding:12px 14px;">暂无年度收益数据。</div>'
    body = []
    for _, row in yearly_return.iterrows():
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row['year']))}</td>"
            f"<td>{_pct(row['equity_change'])}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>年份</th><th>策略收益</th></tr></thead><tbody>"
        + "\n".join(body)
        + "</tbody></table>"
    )


def render_comparison_table(rows):
    if not rows:
        return '<div class="section-note" style="padding:12px 14px;">暂无候选参数对比数据。</div>'
    body = []
    for row in rows:
        selected = " selected" if row["selected"] else ""
        body.append(
            f'<tr class="{selected}">'
            f'<td>{html.escape(str(row["parameter"]))}</td>'
            f'<td>{html.escape(str(row["cum_value"]))}</td>'
            f'<td>{html.escape(str(row["annual_return"]))}</td>'
            f'<td>{html.escape(str(row["max_drawdown"]))}</td>'
            f'<td>{html.escape(str(row["return_drawdown"]))}</td>'
            f'<td>{html.escape(str(row["win_rate"]))}</td>'
            f'<td>{html.escape(str(row["trade_count"]))}</td>'
            f'<td>{html.escape(str(row["avg_holding"]))}</td>'
            "</tr>"
        )
    return (
        "<table><thead><tr><th>参数</th><th>累积净值</th><th>年化收益</th><th>最大回撤</th>"
        "<th>年化/回撤</th><th>胜率</th><th>开仓次数</th><th>平均持仓</th></tr></thead><tbody>"
        + "\n".join(body)
        + "</tbody></table>"
    )


def build_comparison_chart(analyses, symbol):
    if not analyses:
        return ""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.62, 0.38],
        specs=[[{"type": "xy"}], [{"type": "xy"}]],
    )
    palette = ["#245f9f", "#1f8a5b", "#9b6b1b", "#7f4f9f"]
    for idx, analysis in enumerate(analyses):
        df = analysis["df"]
        parameter_label = str(analysis["para"])
        color = palette[idx % len(palette)]
        width = 2.2 if idx == 0 else 1.4
        dash = None if idx == 0 else "dot"
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["equity_curve"],
                mode="lines",
                name=f"{parameter_label} 净值",
                line=dict(color=color, width=width, dash=dash),
                hovertemplate="%{x}<br>" + parameter_label + " 净值=%{y:.4f}<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["drawdown"],
                mode="lines",
                name=f"{parameter_label} 回撤",
                line=dict(color=color, width=1.0, dash=dash),
                hovertemplate="%{x}<br>" + parameter_label + " 回撤=%{y:.2%}<extra></extra>",
            ),
            row=2,
            col=1,
        )
    benchmark_df = analyses[0]["df"]
    fig.add_trace(
        go.Scatter(
            x=benchmark_df["candle_begin_time"],
            y=benchmark_df["benchmark_equity"],
            mode="lines",
            name=f"{symbol} 买入持有",
            line=dict(color="#6d675f", width=1.1, dash="dash"),
            hovertemplate="%{x}<br>买入持有=%{y:.4f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.update_layout(
        template="none",
        height=560,
        autosize=True,
        margin=dict(l=52, r=30, t=24, b=36),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=11)),
        font=dict(family='Georgia, "Times New Roman", "Songti SC", serif', size=12, color="#161616"),
    )
    fig.update_yaxes(title_text="净值", gridcolor="#ece4d8", row=1, col=1)
    fig.update_yaxes(title_text="回撤", tickformat=".0%", gridcolor="#ece4d8", row=2, col=1)
    fig.update_xaxes(showgrid=True, gridcolor="#ece4d8")
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"displaylogo": False, "responsive": True, "scrollZoom": True},
    )


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


def draw_strategy_visualization(df, signal_name, symbol, rule_type, para, path, show=False, analysis=None):
    fig = make_subplots(
        rows=5,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[0.44, 0.18, 0.14, 0.13, 0.11],
        specs=[
            [{"type": "xy"}],
            [{"type": "xy"}],
            [{"type": "xy"}],
            [{"type": "xy", "secondary_y": True}],
            [{"type": "xy"}],
        ],
    )

    fig.add_trace(
            go.Candlestick(
            x=df["candle_begin_time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
                name="ETH K线",
                increasing_line_color="#1f8a5b",
                decreasing_line_color="#c64a3a",
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
                hovertemplate="%{x}<br>" + col + "=%{y:.4f}<extra></extra>",
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
                marker=dict(
                    symbol=style["symbol"],
                    color=style["color"],
                    size=style.get("size", 10),
                    line=dict(width=1, color="white"),
                ),
                customdata=marker_df[["signal", "pos"]].to_numpy() if "pos" in marker_df.columns else marker_df[["signal"]].to_numpy(),
                hovertemplate="%{x}<br>%{fullData.name}<br>price=%{y:.4f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    if "equity_curve" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["equity_curve"],
                mode="lines",
                name="策略净值",
                line=dict(color="#245f9f", width=1.8),
                hovertemplate="%{x}<br>策略净值=%{y:.4f}<extra></extra>",
            ),
            row=2,
            col=1,
        )
    if "benchmark_equity" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["benchmark_equity"],
                mode="lines",
                name="ETH买入持有",
                line=dict(color="#9b6b1b", width=1.2, dash="dot"),
                hovertemplate="%{x}<br>买入持有=%{y:.4f}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    if "drawdown" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["drawdown"],
                mode="lines",
                name="策略回撤",
                line=dict(color="#c64a3a", width=1.2),
                fill="tozeroy",
                fillcolor="rgba(198,74,58,0.18)",
                hovertemplate="%{x}<br>策略回撤=%{y:.2%}<extra></extra>",
            ),
            row=3,
            col=1,
        )
    if "benchmark_drawdown" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["benchmark_drawdown"],
                mode="lines",
                name="买入持有回撤",
                line=dict(color="#9b6b1b", width=1.0, dash="dot"),
                hovertemplate="%{x}<br>买入持有回撤=%{y:.2%}<extra></extra>",
            ),
            row=3,
            col=1,
        )

    if "m" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["m"],
                mode="lines",
                name="动态带宽 m",
                line=dict(color="#245f9f", width=1.1),
                hovertemplate="%{x}<br>m=%{y:.4f}<extra></extra>",
            ),
            row=4,
            col=1,
            secondary_y=False,
        )
    if "bias" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["bias"],
                mode="lines",
                name="bias",
                line=dict(color="#1f8a5b", width=0.9),
                hovertemplate="%{x}<br>bias=%{y:.2%}<extra></extra>",
            ),
            row=4,
            col=1,
            secondary_y=True,
        )
    if "fast_bias" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["fast_bias"],
                mode="lines",
                name="fast_n bias",
                line=dict(color="#7a3db8", width=0.9, dash="dash"),
                hovertemplate="%{x}<br>fast_n bias=%{y:.2%}<extra></extra>",
            ),
            row=4,
            col=1,
            secondary_y=True,
        )
    if "bias_pct" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=df["bias_pct"],
                mode="lines",
                name="bias过滤阈值",
                line=dict(color="#c64a3a", width=0.9, dash="dot"),
                hovertemplate="%{x}<br>bias_pct=%{y:.2%}<extra></extra>",
            ),
            row=4,
            col=1,
            secondary_y=True,
        )
        fig.add_trace(
            go.Scatter(
                x=df["candle_begin_time"],
                y=-df["bias_pct"],
                mode="lines",
                name="-bias过滤阈值",
                line=dict(color="#c64a3a", width=0.9, dash="dot"),
                hovertemplate="%{x}<br>-bias_pct=%{y:.2%}<extra></extra>",
            ),
            row=4,
            col=1,
            secondary_y=True,
        )

    fig.add_trace(
        go.Bar(
            x=df["candle_begin_time"],
            y=df["volume"],
            name="成交量",
            marker=dict(color="rgba(36,95,159,0.28)"),
        ),
        row=5,
        col=1,
    )

    fig.update_layout(
        template="none",
        hovermode="x unified",
        height=1320,
        autosize=True,
        margin=dict(l=52, r=42, t=30, b=45),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        xaxis_rangeslider=dict(visible=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, font=dict(size=11)),
        font=dict(family='Georgia, "Times New Roman", "Songti SC", serif', size=12, color="#161616"),
    )
    grid_color = "#ece4d8"
    fig.update_yaxes(title_text="价格/轨道", gridcolor=grid_color, row=1, col=1)
    fig.update_yaxes(title_text="净值", gridcolor=grid_color, row=2, col=1)
    fig.update_yaxes(title_text="回撤", tickformat=".0%", gridcolor=grid_color, row=3, col=1)
    fig.update_yaxes(title_text="m", gridcolor=grid_color, row=4, col=1, secondary_y=False)
    fig.update_yaxes(title_text="bias", tickformat=".0%", gridcolor=grid_color, row=4, col=1, secondary_y=True)
    fig.update_yaxes(title_text="成交量", gridcolor=grid_color, row=5, col=1)
    fig.update_xaxes(showgrid=True, gridcolor=grid_color)

    chart_html = fig.to_html(
        full_html=False,
        include_plotlyjs=True,
        config={"displaylogo": False, "responsive": True, "scrollZoom": True},
    )
    if analysis is None:
        html_doc = chart_html
    else:
        cards = render_metric_cards(build_metric_cards(analysis["metrics"], para, analysis["trade"]))
        parameter_table = render_parameter_table(analysis["parameter_rows"])
        trade_table = render_trade_table(analysis["trade"])
        yearly_table = render_yearly_table(analysis["yearly_return"])
        comparison_chart = build_comparison_chart(analysis.get("comparison_analyses", []), symbol)
        comparison_table = render_comparison_table(analysis.get("comparison_rows", []))
        stamp = (
            f"区间 {html.escape(str(df['candle_begin_time'].iloc[0]))} -> "
            f"{html.escape(str(df['candle_begin_time'].iloc[-1]))}<br>"
            f"手续费 {getattr(analysis.get('config', None), 'c_rate', '')}"
        )
        html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(symbol)} {html.escape(signal_name)} {html.escape(str(para))}</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<main class="page">
  <header class="topbar">
    <div>
      <h1>{html.escape(symbol)} · {html.escape(signal_name)} · {html.escape(rule_type)}</h1>
      <div class="subtitle">专业量化策略视图，统一使用当前回测核心函数计算信号、持仓、资金曲线与统计指标。</div>
    </div>
    <div class="stamp">参数 {html.escape(str(para))}<br>{stamp}</div>
  </header>
  <section class="cards">{cards}</section>
  <section class="section">
    <div class="section-title">
      <span>策略行为视图</span>
      <span class="section-note">K线/轨道、策略净值、回撤、动态带宽与乖离过滤、成交量</span>
    </div>
    <div class="chart-wrap">{chart_html}</div>
  </section>
  <section class="section">
    <div class="section-title">
      <span>候选参数对比</span>
      <span class="section-note">自动取当前参数与参数平原排名靠前参数，统一回测口径重算净值和回撤</span>
    </div>
    <div class="comparison-wrap">{comparison_chart}</div>
    {comparison_table}
  </section>
  <div class="grid-2">
    <section class="section">
      <div class="section-title"><span>参数平原排名</span><span class="section-note">按年化收益/回撤比排序，当前参数高亮</span></div>
      {parameter_table}
    </section>
    <section class="section">
      <div class="section-title"><span>年度收益拆解</span><span class="section-note">来自策略资金曲线的年度复合收益</span></div>
      {yearly_table}
    </section>
  </div>
  <section class="section">
    <div class="section-title"><span>最差交易检查</span><span class="section-note">按单笔收益从低到高，优先检查风险来源</span></div>
    {trade_table}
  </section>
</main>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html_doc)

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
                parameter_df = load_parameter_result(config, signal_name, symbol, rule_type)
                comparison_analyses = build_comparison_analyses(
                    config, signal_name, symbol, rule_type, config.para, parameter_df
                )
                analysis = comparison_analyses[0]
                analysis["config"] = config
                analysis["comparison_analyses"] = comparison_analyses
                analysis["comparison_rows"] = build_comparison_summary(comparison_analyses, config.para)
                df = analysis["df"]
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
                    analysis=analysis,
                )
                output_paths.append(path)
                print(f"策略可视化已生成: {path}")
    return output_paths
