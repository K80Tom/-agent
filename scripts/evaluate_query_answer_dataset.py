"""把 query_answer Excel 转成 JSON 数据集，并用向量相似度评测命中率。

这个脚本评测的是“评测集内部的向量匹配”：
- 问题侧：使用 Excel 的 `query` 字段作为 query_text。
- 答案侧：使用 answer_asset_id、answer_asset、drama、asset_type、set_id、
  set_name、answer_image_file 拼成 answer_text。
- 评测时：把所有 answer_text 向量化成候选库，再把 query_text 向量化，
  计算 query 向量和每个答案向量的余弦相似度，看正确 answer_asset_id
  是否进入 TopK。

它不会修改数据库，也不会写 Milvus。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.vector.doubao_embedding_service import DoubaoEmbeddingService


DOCS_DIR = Path("docs") / "rag提升文档"
DEFAULT_EXCEL_FILE = Path.home() / "Desktop" / "01_query_answer_20.xlsx"
DEFAULT_DATASET_FILE = DOCS_DIR / "query_answer_20_eval_dataset.json"
DEFAULT_CACHE_FILE = DOCS_DIR / "query_answer_20_embedding_cache.json"
DEFAULT_RESULT_JSON_FILE = DOCS_DIR / "query_answer_20_dataset_eval_result.json"
DEFAULT_RESULT_MD_FILE = DOCS_DIR / "query_answer_20_dataset_eval_result.md"


@dataclass(slots=True)
class EvalCandidate:
    """一个答案候选向量。"""

    answer_asset_id: str
    answer_asset: str
    answer_text: str
    vector: list[float]


def clean_text(value: Any) -> str:
    """把 Excel 单元格值转成稳定字符串。"""

    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def markdown_cell(value: Any) -> str:
    """避免 Markdown 表格被换行和竖线撑坏。"""

    return clean_text(value).replace("|", "\\|")


def build_answer_text(row: dict[str, str]) -> str:
    """把答案侧字段拼成可向量化文本。

    用户指定这些字段属于“命中文本”的信息来源。这里保留字段名，
    是为了让 embedding 模型知道每段文本的语义角色。
    """

    parts = [
        ("答案ID", row["answer_asset_id"]),
        ("资产名称", row["answer_asset"]),
        ("剧名", row["drama"]),
        ("资产类型", row["asset_type"]),
        ("集合ID", row["set_id"]),
        ("集合名称", row["set_name"]),
        ("答案图片", row["answer_image_file"]),
    ]
    return "\n".join(f"{label}：{value}" for label, value in parts if value)


def load_excel_rows(excel_file: Path) -> list[dict[str, str]]:
    """读取 Excel 的 query_answer 工作表。"""

    workbook = openpyxl.load_workbook(excel_file, data_only=True)
    worksheet = workbook["query_answer"]
    headers = [clean_text(cell.value) for cell in worksheet[1]]
    required_headers = {
        "query_id",
        "query",
        "answer_asset_id",
        "answer_asset",
        "drama",
        "asset_type",
        "set_id",
        "set_name",
        "answer_image_file",
    }
    missing_headers = sorted(required_headers.difference(headers))
    if missing_headers:
        raise ValueError(f"Excel 缺少必要列：{', '.join(missing_headers)}")

    rows: list[dict[str, str]] = []
    header_index = {header: index for index, header in enumerate(headers)}
    for values in worksheet.iter_rows(min_row=2, values_only=True):
        if not any(values):
            continue
        row = {
            header: clean_text(values[index])
            for header, index in header_index.items()
            if header in required_headers
        }
        rows.append(row)

    return rows


def build_dataset(excel_file: Path, dataset_file: Path) -> dict[str, Any]:
    """从 Excel 生成 JSON 评测集。"""

    rows = load_excel_rows(excel_file)
    cases = []
    for row in rows:
        cases.append(
            {
                "query_id": row["query_id"],
                "query_text": row["query"],
                "answer": {
                    "answer_asset_id": row["answer_asset_id"],
                    "answer_asset": row["answer_asset"],
                    "drama": row["drama"],
                    "asset_type": row["asset_type"],
                    "set_id": row["set_id"],
                    "set_name": row["set_name"],
                    "answer_image_file": row["answer_image_file"],
                    "answer_text": build_answer_text(row),
                },
            }
        )

    dataset = {
        "dataset_name": excel_file.stem,
        "source_excel": str(excel_file),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "vectorization_rule": {
            "query_text": "使用 query 字段原文向量化。",
            "answer_text": (
                "使用 answer_asset_id、answer_asset、drama、asset_type、"
                "set_id、set_name、answer_image_file 拼接后向量化。"
            ),
            "hit_rule": "按 answer_asset_id 判断正确答案是否进入 TopK。",
        },
        "cases": cases,
    }

    dataset_file.parent.mkdir(parents=True, exist_ok=True)
    dataset_file.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dataset


def load_dataset(dataset_file: Path) -> dict[str, Any]:
    """读取 JSON 评测集。"""

    return json.loads(dataset_file.read_text(encoding="utf-8"))


def load_embedding_cache(cache_file: Path) -> dict[str, list[float]]:
    """读取本地 embedding 缓存，避免重复调用 embedding 接口。"""

    if not cache_file.exists():
        return {}
    raw_cache = json.loads(cache_file.read_text(encoding="utf-8"))
    return {key: [float(item) for item in value] for key, value in raw_cache.items()}


def save_embedding_cache(cache_file: Path, cache: dict[str, list[float]]) -> None:
    """保存 embedding 缓存。"""

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(cache, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_embedding(
    *,
    service: DoubaoEmbeddingService,
    cache: dict[str, list[float]],
    text: str,
    cache_prefix: str,
) -> list[float]:
    """向量化文本，并按文本内容缓存结果。"""

    cache_key = f"{cache_prefix}:{text}"
    if cache_key not in cache:
        cache[cache_key] = service.embed_text(text)
    return cache[cache_key]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """计算余弦相似度。"""

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def build_candidates(
    *,
    dataset: dict[str, Any],
    embedding_service: DoubaoEmbeddingService,
    cache: dict[str, list[float]],
) -> list[EvalCandidate]:
    """把 JSON 中所有标准答案向量化成候选库。"""

    candidates: list[EvalCandidate] = []
    for case in dataset["cases"]:
        answer = case["answer"]
        answer_text = answer["answer_text"]
        vector = get_embedding(
            service=embedding_service,
            cache=cache,
            text=answer_text,
            cache_prefix="answer",
        )
        candidates.append(
            EvalCandidate(
                answer_asset_id=answer["answer_asset_id"],
                answer_asset=answer["answer_asset"],
                answer_text=answer_text,
                vector=vector,
            )
        )
    return candidates


def evaluate_dataset(
    *,
    dataset: dict[str, Any],
    top_k: int,
    cache_file: Path,
    result_json_file: Path,
    result_md_file: Path,
) -> dict[str, Any]:
    """向量化 query 和 answer_text，并计算 Hit@K / MRR。"""

    embedding_service = DoubaoEmbeddingService()
    cache = load_embedding_cache(cache_file)
    candidates = build_candidates(
        dataset=dataset,
        embedding_service=embedding_service,
        cache=cache,
    )

    eval_items = []
    for case in dataset["cases"]:
        query_vector = get_embedding(
            service=embedding_service,
            cache=cache,
            text=case["query_text"],
            cache_prefix="query",
        )
        ranked = sorted(
            (
                {
                    "answer_asset_id": candidate.answer_asset_id,
                    "answer_asset": candidate.answer_asset,
                    "score": cosine_similarity(query_vector, candidate.vector),
                }
                for candidate in candidates
            ),
            key=lambda item: item["score"],
            reverse=True,
        )

        expected_id = case["answer"]["answer_asset_id"]
        hit_rank = None
        hit_score = None
        for rank, item in enumerate(ranked, start=1):
            if item["answer_asset_id"] == expected_id:
                hit_rank = rank
                hit_score = item["score"]
                break

        eval_items.append(
            {
                "query_id": case["query_id"],
                "query_text": case["query_text"],
                "expected_answer_asset_id": expected_id,
                "expected_answer_asset": case["answer"]["answer_asset"],
                "hit_rank": hit_rank,
                "hit_score": hit_score,
                "hit_at_top_k": hit_rank is not None and hit_rank <= top_k,
                "top_k": ranked[:top_k],
            }
        )

    total = len(eval_items)
    hit_count = sum(1 for item in eval_items if item["hit_at_top_k"])
    hit_at_1 = sum(1 for item in eval_items if item["hit_rank"] == 1)
    hit_at_3 = sum(
        1 for item in eval_items if item["hit_rank"] is not None and item["hit_rank"] <= 3
    )
    mrr = sum(
        0.0 if item["hit_rank"] is None else 1.0 / item["hit_rank"]
        for item in eval_items
    ) / total

    result = {
        "dataset_name": dataset["dataset_name"],
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "top_k": top_k,
        "metrics": {
            "total": total,
            "hit_count": hit_count,
            "hit_at_k": hit_count / total if total else 0.0,
            "hit_at_1": hit_at_1 / total if total else 0.0,
            "hit_at_3": hit_at_3 / total if total else 0.0,
            "mrr": mrr,
        },
        "items": eval_items,
    }

    result_json_file.parent.mkdir(parents=True, exist_ok=True)
    result_json_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown_report(result=result, result_md_file=result_md_file)
    save_embedding_cache(cache_file, cache)
    return result


def write_markdown_report(*, result: dict[str, Any], result_md_file: Path) -> None:
    """把评测结果写成方便人工查看的 Markdown。"""

    metrics = result["metrics"]
    lines = [
        "# query_answer_20 JSON 向量评测结果",
        "",
        f"- 数据集：`{result['dataset_name']}`",
        f"- TopK：`{result['top_k']}`",
        f"- 评测时间：{result['evaluated_at']}",
        "",
        "## 指标",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| total | {metrics['total']} |",
        f"| hit_count | {metrics['hit_count']} |",
        f"| Hit@{result['top_k']} | {metrics['hit_at_k']:.2%} |",
        f"| Hit@1 | {metrics['hit_at_1']:.2%} |",
        f"| Hit@3 | {metrics['hit_at_3']:.2%} |",
        f"| MRR | {metrics['mrr']:.4f} |",
        "",
        "## 明细",
        "",
        "| Query ID | 标准答案 | 命中排名 | 命中分数 | Top1 | Top1 分数 | Top5 |",
        "|---|---|---:|---:|---|---:|---|",
    ]

    for item in result["items"]:
        top_items = item["top_k"]
        top1 = top_items[0] if top_items else {}
        top5_text = "；".join(
            f"{rank}.{candidate['answer_asset']}({candidate['score']:.4f})"
            for rank, candidate in enumerate(top_items, start=1)
        )
        hit_rank = item["hit_rank"] if item["hit_rank"] is not None else ""
        hit_score = (
            f"{item['hit_score']:.6f}" if item["hit_score"] is not None else ""
        )
        lines.append(
            "| {query_id} | {expected} | {hit_rank} | {hit_score} | {top1} | {top1_score} | {top5} |".format(
                query_id=markdown_cell(item["query_id"]),
                expected=markdown_cell(item["expected_answer_asset"]),
                hit_rank=hit_rank,
                hit_score=hit_score,
                top1=markdown_cell(top1.get("answer_asset", "")),
                top1_score=(
                    f"{top1['score']:.6f}" if "score" in top1 else ""
                ),
                top5=markdown_cell(top5_text),
            )
        )

    result_md_file.parent.mkdir(parents=True, exist_ok=True)
    result_md_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build JSON eval dataset from query_answer Excel and evaluate vector hit rate."
    )
    parser.add_argument(
        "--mode",
        choices=["build", "evaluate", "all"],
        default="all",
        help="build 只生成 JSON；evaluate 只评测已有 JSON；all 先生成 JSON 再评测。",
    )
    parser.add_argument(
        "--excel",
        default=str(DEFAULT_EXCEL_FILE),
        help="query_answer Excel 文件路径。",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_FILE),
        help="输出/读取的 JSON 数据集路径。",
    )
    parser.add_argument(
        "--cache-file",
        default=str(DEFAULT_CACHE_FILE),
        help="embedding 缓存文件路径。",
    )
    parser.add_argument(
        "--result-json",
        default=str(DEFAULT_RESULT_JSON_FILE),
        help="评测结果 JSON 输出路径。",
    )
    parser.add_argument(
        "--result-md",
        default=str(DEFAULT_RESULT_MD_FILE),
        help="评测结果 Markdown 输出路径。",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="计算 Hit@K 时使用的 K。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    excel_file = Path(args.excel)
    dataset_file = Path(args.dataset)

    if args.mode in {"build", "all"}:
        dataset = build_dataset(excel_file=excel_file, dataset_file=dataset_file)
        print(f"WROTE dataset: {dataset_file} cases={len(dataset['cases'])}")

    if args.mode in {"evaluate", "all"}:
        dataset = load_dataset(dataset_file)
        result = evaluate_dataset(
            dataset=dataset,
            top_k=args.top_k,
            cache_file=Path(args.cache_file),
            result_json_file=Path(args.result_json),
            result_md_file=Path(args.result_md),
        )
        metrics = result["metrics"]
        print("=== Dataset Vector Eval Summary ===")
        print(f"total={metrics['total']}")
        print(f"hit_count={metrics['hit_count']}")
        print(f"hit@{args.top_k}={metrics['hit_at_k']:.2%}")
        print(f"hit@1={metrics['hit_at_1']:.2%}")
        print(f"hit@3={metrics['hit_at_3']:.2%}")
        print(f"mrr={metrics['mrr']:.4f}")
        print(f"WROTE result json: {args.result_json}")
        print(f"WROTE result md: {args.result_md}")


if __name__ == "__main__":
    main()
