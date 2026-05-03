import argparse
import os
import warnings
from multiprocessing import cpu_count, get_context

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import (
    c_rate,
    data_path,
    date_end,
    date_start,
    leverage_rate,
    min_amount_dict,
    min_margin_ratio,
    root_path,
    slippage,
)
from cta_api.function import cal_equity_curve
from cta_api.position import position_for_future
from cta_api.statistics import strategy_evaluate, transfer_equity_curve_to_trade


SIGNAL_NAME = "adapt_bolling_anti_chase"
SYMBOL = "ETH-USDT"
RULE_TYPE = "4H"
N_VALUES = list(range(10, 1000 + 10, 10))
BIAS_VALUES = list(range(5, 50 + 5, 5))
SOURCE_DF = None
MIN_AMOUNT = None


def init_worker(df, min_amount):
    global SOURCE_DF, MIN_AMOUNT
    SOURCE_DF = df
    MIN_AMOUNT = min_amount


def pct_to_float(value):
    if pd.isna(value):
        return None
    if isinstance(value, str) and value.endswith("%"):
        return float(value.rstrip("%")) / 100
    return float(value)


def run_one(args):
    n, max_fast_bias_pct = args
    warnings.filterwarnings("ignore")
    cls = __import__(f"factors.{SIGNAL_NAME}", fromlist=("",))
    _df = SOURCE_DF.copy()
    _df = cls.signal(_df, para=[n, max_fast_bias_pct], proportion=0.05, leverage_rate=leverage_rate)
    _df = position_for_future(_df)
    _df = _df[
        (_df["candle_begin_time"] >= pd.to_datetime(date_start))
        & (_df["candle_begin_time"] <= pd.to_datetime(date_end))
    ]

    try:
        _df = cal_equity_curve(
            _df,
            slippage=slippage,
            c_rate=c_rate,
            leverage_rate=leverage_rate,
            min_amount=MIN_AMOUNT,
            min_margin_ratio=min_margin_ratio,
        )
    except Exception as exc:
        return {
            "n": n,
            "max_fast_bias_pct": max_fast_bias_pct,
            "error": str(exc),
        }

    sub = _df[
        (_df["candle_begin_time"] >= pd.to_datetime("2021-05-01"))
        & (_df["candle_begin_time"] <= pd.to_datetime("2021-07-31"))
    ].copy()
    local_drawdown = (sub["equity_curve"] / sub["equity_curve"].cummax() - 1).min()
    block_count = int(_df.get("anti_chase_block_trigger", pd.Series(False, index=_df.index)).sum())

    trade = transfer_equity_curve_to_trade(_df)
    if trade.empty:
        return {
            "n": n,
            "max_fast_bias_pct": max_fast_bias_pct,
            "error": "empty_trade",
        }

    stats, _ = strategy_evaluate(_df, trade, RULE_TYPE)
    row = {idx: stats.loc[idx, 0] for idx in stats.index}
    row.update(
        {
            "n": n,
            "max_fast_bias_pct": max_fast_bias_pct,
            "max_fast_bias": max_fast_bias_pct / 100,
            "para": str([n, max_fast_bias_pct]),
            "开仓次数": len(trade),
            "追单过滤次数": block_count,
            "2021_05_局部回撤_num": local_drawdown,
            "年化收益_num": float(row["年化收益"]),
            "最大回撤_num": pct_to_float(row["最大回撤"]),
            "胜率_num": pct_to_float(row["胜率"]),
            "年化收益/回撤比_num": float(row["年化收益/回撤比"]),
            "累积净值_num": float(row["累积净值"]),
            "单笔最大盈利_num": pct_to_float(row["单笔最大盈利"]),
            "单笔最大亏损_num": pct_to_float(row["单笔最大亏损"]),
            "回测区间": f"{date_start}_{date_end}",
            "error": "",
        }
    )
    return row


def add_sharpness_metrics(result_df):
    df = result_df.copy()
    score_map = {
        (int(row["n"]), int(row["max_fast_bias_pct"])): float(row["年化收益/回撤比_num"])
        for _, row in df.iterrows()
    }
    n_step = 10
    bias_step = 5
    sharpness = []
    neighbor_mean = []
    neighbor_median = []
    neighbor_count = []
    plateau_score = []

    for _, row in df.iterrows():
        values = []
        for dn in (-n_step, 0, n_step):
            for db in (-bias_step, 0, bias_step):
                if dn == 0 and db == 0:
                    continue
                value = score_map.get((int(row["n"]) + dn, int(row["max_fast_bias_pct"]) + db))
                if value is not None:
                    values.append(value)
        score = float(row["年化收益/回撤比_num"])
        mean_value = pd.Series(values).mean() if values else score
        median_value = pd.Series(values).median() if values else score
        local_sharpness = score - mean_value
        sharpness.append(local_sharpness)
        neighbor_mean.append(mean_value)
        neighbor_median.append(median_value)
        neighbor_count.append(len(values))
        plateau_score.append(score * 0.45 + median_value * 0.45 - max(local_sharpness, 0) * 0.25)

    df["邻居收益回撤均值"] = neighbor_mean
    df["邻居收益回撤中位数"] = neighbor_median
    df["邻居数量"] = neighbor_count
    df["参数锐度值"] = sharpness
    df["参数锐度绝对值"] = df["参数锐度值"].abs()
    df["参数平原分"] = plateau_score
    return df


def pivot_metric(df, metric):
    pivot = df.pivot(index="max_fast_bias_pct", columns="n", values=metric)
    pivot.sort_index(ascending=True, inplace=True)
    return pivot


def format_pct(series):
    return series.map(lambda x: f"{x:.2%}")


def build_heatmap(result_df, output_path):
    ratio_pivot = pivot_metric(result_df, "年化收益/回撤比_num")
    equity_pivot = pivot_metric(result_df, "累积净值_num")
    drawdown_pivot = pivot_metric(result_df, "最大回撤_num")
    sharpness_pivot = pivot_metric(result_df, "参数锐度值")
    plateau_pivot = pivot_metric(result_df, "参数平原分")

    top_score = result_df.sort_values("年化收益/回撤比_num", ascending=False).head(20)
    top_plateau = result_df.sort_values("参数平原分", ascending=False).head(20)
    low_sharp_top = (
        result_df[result_df["年化收益/回撤比_num"] >= result_df["年化收益/回撤比_num"].quantile(0.85)]
        .sort_values(["参数锐度绝对值", "年化收益/回撤比_num"], ascending=[True, False])
        .head(20)
    )

    fig = make_subplots(
        rows=5,
        cols=2,
        specs=[
            [{"type": "heatmap", "colspan": 2}, None],
            [{"type": "heatmap", "colspan": 2}, None],
            [{"type": "heatmap"}, {"type": "heatmap"}],
            [{"type": "heatmap", "colspan": 2}, None],
            [{"type": "table"}, {"type": "table"}],
        ],
        subplot_titles=[
            "年化收益/回撤比参数平原",
            "累积净值参数平原",
            "最大回撤参数平原",
            "参数锐度值",
            "参数平原分",
            "Top 20 收益/回撤",
            "Top 20 平原分",
        ],
        vertical_spacing=0.055,
        horizontal_spacing=0.08,
        row_heights=[0.23, 0.20, 0.18, 0.18, 0.21],
    )

    fig.add_trace(
        go.Heatmap(
            x=ratio_pivot.columns,
            y=ratio_pivot.index,
            z=ratio_pivot.values,
            colorscale="RdYlGn",
            colorbar=dict(title="收益/回撤", x=1.01, y=0.92, len=0.20),
            hovertemplate="n=%{x}<br>追单阈值=%{y}%<br>收益/回撤=%{z:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Heatmap(
            x=equity_pivot.columns,
            y=equity_pivot.index,
            z=equity_pivot.values,
            colorscale="Blues",
            colorbar=dict(title="净值", x=1.01, y=0.69, len=0.16),
            hovertemplate="n=%{x}<br>追单阈值=%{y}%<br>累积净值=%{z:.2f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Heatmap(
            x=drawdown_pivot.columns,
            y=drawdown_pivot.index,
            z=drawdown_pivot.values,
            colorscale="RdYlGn",
            colorbar=dict(title="回撤", x=0.46, y=0.48, len=0.14),
            hovertemplate="n=%{x}<br>追单阈值=%{y}%<br>最大回撤=%{z:.2%}<extra></extra>",
        ),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Heatmap(
            x=sharpness_pivot.columns,
            y=sharpness_pivot.index,
            z=sharpness_pivot.values,
            colorscale="RdBu",
            zmid=0,
            colorbar=dict(title="锐度", x=1.01, y=0.48, len=0.14),
            hovertemplate="n=%{x}<br>追单阈值=%{y}%<br>锐度=%{z:.3f}<extra></extra>",
        ),
        row=3,
        col=2,
    )
    fig.add_trace(
        go.Heatmap(
            x=plateau_pivot.columns,
            y=plateau_pivot.index,
            z=plateau_pivot.values,
            colorscale="Viridis",
            colorbar=dict(title="平原分", x=1.01, y=0.29, len=0.14),
            hovertemplate="n=%{x}<br>追单阈值=%{y}%<br>平原分=%{z:.2f}<extra></extra>",
        ),
        row=4,
        col=1,
    )
    fig.add_trace(build_table(top_score, "收益/回撤"), row=5, col=1)
    fig.add_trace(build_table(top_plateau, "平原分"), row=5, col=2)

    fig.update_layout(
        title=(
            f"{SYMBOL} {SIGNAL_NAME} {RULE_TYPE} 二维参数平原与锐度"
            f"<br><sup>区间 {date_start} -> {date_end}；stop_loss固定0.05；"
            f"锐度=当前收益/回撤比 - 周围8邻居均值，越高越像孤峰</sup>"
        ),
        height=1900,
        width=1600,
        template="plotly_white",
        hovermode="closest",
        margin=dict(l=70, r=100, t=115, b=60),
    )
    fig.update_xaxes(title_text="n")
    fig.update_yaxes(title_text="max_fast_bias_pct")
    fig.write_html(output_path)

    low_sharp_path = output_path.replace(".html", "_low_sharp_top.csv")
    low_sharp_top.to_csv(low_sharp_path, index=False, encoding="gbk")


def build_table(rows, rank_name):
    return go.Table(
        header=dict(
            values=["排名", "n", "阈值", "净值", "最大回撤", "收益/回撤", "锐度", "平原分", "最大盈利", "过滤次数", "交易数"],
            fill_color="#0f172a",
            font=dict(color="white", size=12),
            align="center",
        ),
        cells=dict(
            values=[
                list(range(1, len(rows) + 1)),
                rows["n"],
                rows["max_fast_bias_pct"].map(lambda x: f"{x}%"),
                rows["累积净值_num"].map(lambda x: f"{x:.2f}"),
                format_pct(rows["最大回撤_num"]),
                rows["年化收益/回撤比_num"].map(lambda x: f"{x:.2f}"),
                rows["参数锐度值"].map(lambda x: f"{x:.3f}"),
                rows["参数平原分"].map(lambda x: f"{x:.2f}"),
                format_pct(rows["单笔最大盈利_num"]),
                rows["追单过滤次数"],
                rows["开仓次数"],
            ],
            fill_color="#f8fafc",
            align="center",
            height=24,
        ),
        name=rank_name,
    )


def main():
    global SYMBOL, RULE_TYPE, date_start, date_end

    parser = argparse.ArgumentParser(description="Scan anti-chase plateaus for adapt_bolling.")
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--rule-type", default=RULE_TYPE)
    parser.add_argument("--date-start", default=date_start)
    parser.add_argument("--date-end", default=date_end)
    parser.add_argument("--processes", type=int, default=max(cpu_count() - 1, 1))
    parser.add_argument("--n-values", default=",".join(str(value) for value in N_VALUES))
    parser.add_argument("--bias-values", default=",".join(str(value) for value in BIAS_VALUES))
    args = parser.parse_args()

    SYMBOL = args.symbol
    RULE_TYPE = args.rule_type
    date_start = args.date_start
    date_end = args.date_end
    n_values = [int(value.strip()) for value in args.n_values.split(",") if value.strip()]
    bias_values = [int(value.strip()) for value in args.bias_values.split(",") if value.strip()]
    tasks = [(n, bias) for bias in bias_values for n in n_values]
    df = pd.read_feather(os.path.join(data_path, RULE_TYPE, f"{SYMBOL}.pkl"))
    min_amount = min_amount_dict[SYMBOL]

    rows = []
    ctx = get_context("fork")
    with ctx.Pool(max(args.processes, 1), initializer=init_worker, initargs=(df, min_amount)) as pool:
        for index, row in enumerate(pool.imap_unordered(run_one, tasks, chunksize=10), start=1):
            rows.append(row)
            if index % 100 == 0 or index == len(tasks):
                print(f"progress={index}/{len(tasks)}", flush=True)

    result_df = pd.DataFrame(rows)
    result_df = result_df[result_df["error"].fillna("") == ""].copy()
    result_df = add_sharpness_metrics(result_df)
    result_df.sort_values(["年化收益/回撤比_num", "累积净值_num"], ascending=False, inplace=True)

    output_dir = os.path.join(root_path, "data/output/anti_chase_plain")
    os.makedirs(output_dir, exist_ok=True)
    result_path = os.path.join(output_dir, f"{SIGNAL_NAME}_{SYMBOL}_{RULE_TYPE}_grid.csv")
    html_path = os.path.join(output_dir, f"{SIGNAL_NAME}_{SYMBOL}_{RULE_TYPE}_plain.html")
    plateau_path = os.path.join(output_dir, f"{SIGNAL_NAME}_{SYMBOL}_{RULE_TYPE}_plateau_top.csv")

    result_df.to_csv(result_path, index=False, encoding="gbk")
    result_df.sort_values("参数平原分", ascending=False).head(100).to_csv(plateau_path, index=False, encoding="gbk")
    build_heatmap(result_df, html_path)

    print(f"grid_rows={len(result_df)}")
    print(f"grid_csv={result_path}")
    print(f"plateau_top_csv={plateau_path}")
    print(f"html={html_path}")
    print("top10_by_return_drawdown")
    print(
        result_df[
            [
                "n",
                "max_fast_bias_pct",
                "累积净值_num",
                "最大回撤_num",
                "年化收益/回撤比_num",
                "参数锐度值",
                "参数平原分",
                "追单过滤次数",
                "开仓次数",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )
    print("top10_by_plateau")
    print(
        result_df.sort_values("参数平原分", ascending=False)[
            [
                "n",
                "max_fast_bias_pct",
                "累积净值_num",
                "最大回撤_num",
                "年化收益/回撤比_num",
                "参数锐度值",
                "参数平原分",
                "追单过滤次数",
                "开仓次数",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
