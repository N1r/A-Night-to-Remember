"""
Eval Reporter - 截面评估报告
===========================
用于格式化输出 MonthlyRollingEvaluator 的评测结果以及多期聚合结果。
"""

import pandas as pd
from typing import List, Dict
from rich.console import Console
from rich.table import Table

from .rolling_evaluator import EvalResult

console = Console()

def generate_eval_report(results: List[EvalResult], eval_date_str: str, csv_path: str = "output/eval/rolling_eval.csv") -> Dict:
    """输出单期截面评估报告并返回统计字典供聚合使用"""
    if not results:
        console.print("[yellow]没有找到交易信号或符合条件的标的[/yellow]")
        return {
            "period": eval_date_str,
            "trade_count": 0,
            "win_rate": 0.0,
            "sl_rate": 0.0,
            "avg_return": 0.0,
            "details": []
        }
        
    table = Table(title=f"[bold cyan]SMC 策略截面评估报告 ({eval_date_str})[/bold cyan]", show_lines=True)
    table.add_column("代码", style="cyan")
    table.add_column("名称", style="cyan")
    table.add_column("方向", justify="center")
    table.add_column("评分", justify="right")
    table.add_column("入场价", justify="right")
    table.add_column("最高涨幅", justify="right")
    table.add_column("期末表现", justify="right")
    table.add_column("止盈/止损", justify="center")
    
    hit_tp1_count = 0
    hit_sl_count = 0
    total_end_return = 0.0
    
    dict_list = []
    
    for r in results:
        dir_color = "green" if r.signal_type == "long" else "red"
        max_ret_c = "green" if r.max_return_pct > 0 else "red"
        end_ret_c = "green" if r.end_return_pct > 0 else "red"
        
        status = []
        if r.hit_sl: status.append("[red]SL[/red]")
        if r.hit_tp1: status.append("[green]TP1[/green]")
        if r.hit_tp2: status.append("[bold green]TP2[/bold green]")
        if not status: status.append("持平/未达")
        
        table.add_row(
            r.symbol,
            r.name,
            f"[{dir_color}]{r.signal_type.upper()}[/{dir_color}]",
            f"{r.overall_score:.1f}",
            f"{r.entry_price:.2f}",
            f"[{max_ret_c}]{r.max_return_pct:.2f}%[/{max_ret_c}]",
            f"[{end_ret_c}]{r.end_return_pct:.2f}%[/{end_ret_c}]",
            " / ".join(status)
        )
        
        if r.hit_tp1: hit_tp1_count += 1
        if r.hit_sl: hit_sl_count += 1
        total_end_return += r.end_return_pct
        
        dict_list.append({
            "Symbol": r.symbol,
            "Name": r.name,
            "Date": r.eval_date,
            "Direction": r.signal_type,
            "Score": r.overall_score,
            "Entry": r.entry_price,
            "ForwardDays": r.forward_days,
            "MaxRet%": r.max_return_pct,
            "EndRet%": r.end_return_pct,
            "HitSL": r.hit_sl,
            "HitTP1": r.hit_tp1,
            "HitTP2": r.hit_tp2
        })
        
    console.print()
    console.print(table)
    
    avg_return = total_end_return / len(results) if results else 0
    win_rate = hit_tp1_count / len(results) * 100 if results else 0
    sl_rate = hit_sl_count / len(results) * 100 if results else 0
    
    sum_table = Table(title="[bold]当期组合表现统计[/bold]")
    sum_table.add_column("标的数量", justify="right")
    sum_table.add_column("触及止盈1 (TP1) 胜率", justify="right")
    sum_table.add_column("触碰止损 (SL) 率", justify="right")
    sum_table.add_column("组合等权期末均收益", justify="right")
    
    avg_ret_c = "green" if avg_return > 0 else "red"
    
    sum_table.add_row(
        str(len(results)),
        f"{win_rate:.1f}%",
        f"{sl_rate:.1f}%",
        f"[{avg_ret_c}]{avg_return:.2f}%[/{avg_ret_c}]"
    )
    
    console.print()
    console.print(sum_table)
    console.print()
    
    if dict_list and csv_path:
        import os
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        pd.DataFrame(dict_list).to_csv(csv_path, index=False, encoding="utf-8-sig")
        console.print(f"[dim]当期测试明细已保存至: {csv_path}[/dim]")
        
    return {
        "period": eval_date_str,
        "trade_count": len(results),
        "win_rate": win_rate,
        "sl_rate": sl_rate,
        "avg_return": avg_return,
        "details": dict_list  # 增加明细数据
    }

def generate_aggregated_report(period_stats: List[Dict], csv_path: str = "output/eval/continuous_summary.csv"):
    """输出多期汇总的大盘报告"""
    if not period_stats:
        return
        
    table = Table(title="[bold magenta]SMC 策略连续滚动评估 (汇总报告)[/bold magenta]", show_lines=True)
    table.add_column("评估周期(基准日)", style="magenta")
    table.add_column("信号标的数", justify="right")
    table.add_column("止盈1胜率", justify="right")
    table.add_column("触损率", justify="right")
    table.add_column("截面等权收益", justify="right")
    
    total_trades = 0
    total_return = 0.0
    valid_periods = 0
    total_wins_weighted = 0.0
    
    for stat in reversed(period_stats): # 打印时顺时间排序 (旧->新)
        avg_ret = stat['avg_return']
        ret_c = "green" if avg_ret > 0 else "red"
        
        table.add_row(
            str(stat['period']),
            str(stat['trade_count']),
            f"{stat['win_rate']:.1f}%" if stat['trade_count'] > 0 else "-",
            f"{stat['sl_rate']:.1f}%" if stat['trade_count'] > 0 else "-",
            f"[{ret_c}]{avg_ret:.2f}%[/{ret_c}]" if stat['trade_count'] > 0 else "-"
        )
        
        if stat['trade_count'] > 0:
            total_trades += stat['trade_count']
            total_return += stat['avg_return']
            valid_periods += 1
            total_wins_weighted += stat['trade_count'] * (stat['win_rate']/100)
            
    console.print(table)
    
    overall_avg_return = total_return / valid_periods if valid_periods > 0 else 0.0
    overall_win_rate = (total_wins_weighted / total_trades * 100) if total_trades > 0 else 0.0
    
    sum_table = Table(title="[bold]总体表现统计[/bold]")
    sum_table.add_column("总测试期数", justify="right")
    sum_table.add_column("有效发信号期数", justify="right")
    sum_table.add_column("总信号产生数", justify="right")
    sum_table.add_column("全局平均胜率", justify="right")
    sum_table.add_column("期平均截面收益", justify="right")
    
    ret_c = "green" if overall_avg_return > 0 else "red"
    
    sum_table.add_row(
        str(len(period_stats)),
        str(valid_periods),
        str(total_trades),
        f"{overall_win_rate:.1f}%",
        f"[{ret_c}]{overall_avg_return:.2f}%[/{ret_c}]"
    )
    
    console.print()
    
    # 生成 Markdown 报告
    md_path = csv_path.replace(".csv", ".md") if csv_path else "output/eval/continuous_summary.md"
    generate_markdown_report(period_stats, overall_avg_return, overall_win_rate, valid_periods, total_trades, md_path)
    
    if csv_path:
        import os
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        pd.DataFrame(period_stats).to_csv(csv_path, index=False, encoding="utf-8-sig")
        console.print(f"[dim]已将汇总数据保存至: {csv_path}[/dim]")


def generate_markdown_report(period_stats, overall_avg_ret, overall_win_rate, valid_periods, total_trades, output_path):
    """生成 Markdown 格式的报告总结"""
    lines = [
        "# SMC 策略滚动评估报告",
        "",
        "## 1. 总体表现概览",
        "",
        f"- **总测试期数**: {len(period_stats)}",
        f"- **有效信号期数**: {valid_periods}",
        f"- **总信号产生数**: {total_trades}",
        f"- **全局平均胜率 (TP1)**: {overall_win_rate:.2f}%",
        f"- **组合平均期收益率**: {overall_avg_ret:.2f}%",
        "",
        "## 2. 逐期表现明细",
        "",
        "| 评估周期 (基准日) | 信号标的数量 | 止盈1胜率 | 触损率 | 截面等权收益 |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]
    
    for stat in reversed(period_stats):
        avg_ret_str = f"{stat['avg_return']:.2f}%"
        lines.append(
            f"| {stat['period']} | {stat['trade_count']} | {stat['win_rate']:.1f}% | {stat['sl_rate']:.1f}% | {avg_ret_str} |"
        )
        
    lines.append("")
    lines.append("---")
    
    lines.append("## 3. 逐期选股与表现明细")
    lines.append("")
    
    for stat in reversed(period_stats):
        if not stat['details']:
            continue
            
        lines.append(f"### 📅 评估基准日: {stat['period']}")
        lines.append("")
        lines.append("| 代码 | 名称 | 方向 | 评分 | 入场价 | 最高涨幅 | 期末表现 | 状态 |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        
        for d in stat['details']:
            status = []
            if d['HitSL']: status.append("SL")
            if d['HitTP1']: status.append("TP1")
            if d['HitTP2']: status.append("TP2")
            status_str = " / ".join(status) if status else "持平/未达"
            
            lines.append(
                f"| {d['Symbol']} | {d['Name']} | {d['Direction'].upper()} | {d['Score']:.1f} | {d['Entry']:.2f} | {d['MaxRet%']:.2f}% | {d['EndRet%']:.2f}% | {status_str} |"
            )
        lines.append("")

    lines.append("---")
    lines.append(f"*报告生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    console.print(f"[dim]已生成 Markdown 报告: {output_path}[/dim]")
