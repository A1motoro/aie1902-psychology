#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
心理量表标注助手
用于快速对表现进行心理量表的分数标注，支持批量标注和多种项目格式。
"""

import json
import os
import sys
import argparse
from pathlib import Path


def load_config(config_path: str | None) -> dict:
    """加载配置文件，返回默认配置或文件中的配置。"""
    defaults = {
        "score_range": [0, 3],
        "confidence_range": [1, 3],
        "id_field": "id",
        "response_field": "user_response",
        "score_field": "annotator_score",
        "confidence_field": "annotator_confidence",
    }
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        defaults.update(loaded)
    return defaults


def load_data(file_path: str) -> list:
    """加载 JSON 标注数据。"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("JSON 文件应包含一个数组")
    return data


def save_data(file_path: str, data: list, backup: bool = True) -> None:
    """保存标注数据，可选备份。"""
    if backup and os.path.exists(file_path):
        backup_path = file_path.replace(".json", "_backup.json")
        with open(file_path, "r", encoding="utf-8") as f:
            backup_data = f.read()
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(backup_data)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_first_unannotated(
    data: list, score_field: str, confidence_field: str
) -> int:
    """找到第一个未标注的条目索引。"""
    for i, item in enumerate(data):
        score = item.get(score_field)
        conf = item.get(confidence_field)
        if score is None or conf is None:
            return i
    return len(data)


def count_annotated(data: list, score_field: str, confidence_field: str) -> int:
    """统计已标注数量。"""
    return sum(
        1
        for item in data
        if item.get(score_field) is not None and item.get(confidence_field) is not None
    )


def parse_input(
    text: str,
    score_range: tuple[int, int],
    confidence_range: tuple[int, int],
) -> tuple[int | None, int | None] | None:
    """
    解析用户输入。支持格式：
    - "3 4" -> (3, 4)
    - "3" -> (3, None)，置信度可后续单独输入或使用默认
    - "" 或 "s" -> 跳过
    - "q" -> 退出
    返回 (score, confidence) 或 None 表示跳过/无效。
    """
    text = text.strip()
    if not text:
        return None
    if text.lower() == "q":
        return "quit"
    if text.lower() == "s":
        return "skip"

    parts = text.split()
    try:
        score = int(parts[0])
        if not (score_range[0] <= score <= score_range[1]):
            return None
        confidence = int(parts[1]) if len(parts) > 1 else None
        if confidence is not None and not (
            confidence_range[0] <= confidence <= confidence_range[1]
        ):
            return None
        return (score, confidence)
    except (ValueError, IndexError):
        return None


def run_annotation(
    data_path: str,
    config_path: str | None,
    output_path: str | None,
    start_index: int | None,
) -> None:
    """运行交互式标注流程。"""
    config = load_config(config_path)
    data = load_data(data_path)
    out_path = output_path or data_path

    id_f = config["id_field"]
    resp_f = config["response_field"]
    score_f = config["score_field"]
    conf_f = config["confidence_field"]
    score_min, score_max = config["score_range"]
    conf_min, conf_max = config["confidence_range"]

    total = len(data)
    current = (
        start_index
        if start_index is not None
        else find_first_unannotated(data, score_f, conf_f)
    )

    if current >= total:
        print("所有条目已标注完成。")
        return

    print("\n" + "=" * 60)
    print("心理量表标注助手")
    print("=" * 60)
    print(f"分数范围: {score_min}-{score_max}  置信度范围: {conf_min}-{conf_max}")
    print("输入格式: 分数 [置信度]  (如: 3 4 或 3)")
    print("命令: 回车跳过 | s 跳过 | p 上一条 | q 保存并退出")
    print("=" * 60)

    last_score = None
    while current < total:
        item = data[current]
        item_id = item.get(id_f, current + 1)
        response = item.get(resp_f, "")
        score_val = item.get(score_f)
        conf_val = item.get(conf_f)

        annotated = count_annotated(data, score_f, conf_f)
        print(f"\n[{current + 1}/{total}] 已标注: {annotated}/{total}")
        print(f"ID: {item_id}")
        print(f"用户回应: {response}")
        if score_val is not None:
            print(f"当前: 分数={score_val}, 置信度={conf_val}")

        prompt = "输入分数 [置信度] (或 s 跳过, p 上一条, q 退出): "
        user_input = input(prompt).strip()

        if user_input.lower() == "p":
            if current > 0:
                current -= 1
            else:
                print("已是第一条。")
            continue

        if user_input.lower() == "q":
            save_data(out_path, data)
            print(f"\n已保存至 {out_path}，共标注 {annotated}/{total} 条。")
            return

        if user_input.lower() == "s" or not user_input:
            current += 1
            continue

        parsed = parse_input(user_input, (score_min, score_max), (conf_min, conf_max))
        if parsed == "quit":
            save_data(out_path, data)
            print(f"\n已保存至 {out_path}，共标注 {annotated}/{total} 条。")
            return
        if parsed == "skip":
            current += 1
            continue
        if parsed is None:
            print("输入无效，请重试。")
            continue

        score, confidence = parsed
        if confidence is None:
            confidence = last_score if last_score is not None else conf_max
        last_score = confidence

        item[score_f] = score
        item[conf_f] = confidence
        save_data(out_path, data)
        current += 1

    print(f"\n标注完成！共 {total} 条，已保存至 {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="心理量表标注助手 - 快速标注心理量表分数"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="anotation_example.json",
        help="输入 JSON 文件路径（默认: anotation_example.json）",
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="配置文件路径（可选）",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="输出文件路径（默认覆盖输入文件）",
    )
    parser.add_argument(
        "-s", "--start",
        type=int,
        default=None,
        help="从第几条开始标注（1-based，默认从第一条未标注开始）",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"错误: 文件不存在: {args.input}")
        sys.exit(1)

    start = (args.start - 1) if args.start is not None else None
    run_annotation(args.input, args.config, args.output, start)


if __name__ == "__main__":
    main()
