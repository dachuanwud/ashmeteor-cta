import os
import subprocess
import sys


TASK_ALIASES = {
    "backtest": "backtest",
    "single": "backtest",
    "single_backtest": "backtest",
    "sweep": "sweep",
    "optimize": "sweep",
    "param": "sweep",
    "parameter": "sweep",
    "plot": "plot",
    "evaluate": "plot",
    "parameter_plot": "plot",
    "visualize": "visualize",
    "visualization": "visualize",
    "vis": "visualize",
}

TASK_SCRIPTS = {
    "backtest": "2_fast_backview.py",
    "sweep": "3_fastover.py",
    "plot": "4_strategy_evaluate.py",
    "visualize": "5_strategy_visualize.py",
}


def normalize_task_list(tasks):
    if tasks is None:
        tasks = ["backtest"]
    if isinstance(tasks, str):
        tasks = [task.strip() for task in tasks.split(",") if task.strip()]

    normalized = []
    for task in tasks:
        key = str(task).strip().lower()
        if key not in TASK_ALIASES:
            valid = ", ".join(sorted(TASK_ALIASES))
            raise ValueError(f"未知回测任务: {task}. 可用任务/别名: {valid}")
        normalized.append(TASK_ALIASES[key])
    return normalized


def task_script_names(tasks):
    return [TASK_SCRIPTS[task] for task in normalize_task_list(tasks)]


def print_config_summary(config, tasks):
    print("=== 当前回测配置 ===", flush=True)
    print("任务:", tasks, flush=True)
    print("策略:", getattr(config, "signal_name_list", None), flush=True)
    print("标的:", getattr(config, "symbol_list", None), flush=True)
    print("周期:", getattr(config, "rule_type_list", None), flush=True)
    print("参数:", getattr(config, "para", None), flush=True)
    print("回测区间:", getattr(config, "date_start", None), "->", getattr(config, "date_end", None), flush=True)
    print("分区遍历:", getattr(config, "per_eva", None), flush=True)
    print(flush=True)


def run_configured_tasks(config):
    tasks = normalize_task_list(getattr(config, "run_task_list", ["backtest"]))
    print_config_summary(config, tasks)

    for task, script_name in zip(tasks, task_script_names(tasks)):
        script_path = os.path.join(config.root_path, script_name)
        print(f"=== 执行任务: {task} ({script_name}) ===", flush=True)
        subprocess.run([sys.executable, script_path], cwd=config.root_path, check=True)


def main():
    import config

    run_configured_tasks(config)


if __name__ == "__main__":
    main()
