"""资产语义检索评测脚本。

这个脚本用于离线评估 `/api/v1/asset-search/semantic` 的检索质量。
它不会改数据库，也不会改 Milvus，只会读取一批 query，调用接口，然后计算命中情况。

使用方式：
    python scripts/evaluate_asset_search.py --base-url http://127.0.0.1:8000

评测文件默认读取：
    docs/rag_eval_queries.example.jsonl

JSONL 每一行是一条评测样例，常用字段：
    id: 样例 ID，方便排查
    query: 检索文本
    limit: 请求接口时的返回数量
    expected_source_ids: 期望命中的 source_id 列表，最准
    expected_names: 期望命中的 name/display_name 列表，适合早期没有固定 ID 时使用
    expected_asset_kind: 期望资产类型，例如 character / scene
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_EVAL_FILE = Path("docs") / "rag_eval_queries.example.jsonl"


@dataclass(slots=True)
class EvalCase:
    """一条检索评测样例。

    这里同时支持按 source_id 和按名称判断命中：
    - source_id 最稳定，适合正式评测。
    - expected_names 更方便手工起步，但资产重名时可能不够严格。
    """

    id: str
    query: str
    limit: int = 5
    expected_source_ids: list[str] = field(default_factory=list)
    expected_names: list[str] = field(default_factory=list)
    expected_asset_kind: str | None = None
    tags: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass(slots=True)
class EvalResult:
    """一条样例的评测结果。"""

    case: EvalCase
    hit_rank: int | None
    returned_count: int
    top_items: list[dict[str, Any]]
    error: str | None = None

    @property
    def hit(self) -> bool:
        return self.hit_rank is not None

    @property
    def reciprocal_rank(self) -> float:
        if self.hit_rank is None:
            return 0.0
        return 1.0 / self.hit_rank


def load_eval_cases(path: Path) -> list[EvalCase]:
    """读取 JSONL 评测文件。

    JSONL 的好处是每条样例独立一行，后续追加、删除、人工 review 都很方便。
    """

    cases: list[EvalCase] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        data = json.loads(line)
        try:
            cases.append(
                EvalCase(
                    id=str(data["id"]),
                    query=str(data["query"]),
                    limit=int(data.get("limit", 5)),
                    expected_source_ids=[str(item) for item in data.get("expected_source_ids", [])],
                    expected_names=[str(item) for item in data.get("expected_names", [])],
                    expected_asset_kind=data.get("expected_asset_kind"),
                    tags=[str(item) for item in data.get("tags", [])],
                    note=data.get("note"),
                )
            )
        except KeyError as exc:
            raise ValueError(f"Missing required field {exc} at {path}:{line_number}") from exc

    return cases


def call_search_api(*, base_url: str, query: str, limit: int, timeout_seconds: int) -> dict[str, Any]:
    """调用资产语义检索接口。

    这里使用 Python 标准库 urllib，避免为了评测脚本额外增加依赖。
    """

    endpoint = f"{base_url.rstrip('/')}/api/v1/asset-search/semantic"
    payload = json.dumps(
        {
            "query": query,
            "limit": limit,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    http_request = request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    with request.urlopen(http_request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def find_hit_rank(case: EvalCase, items: list[dict[str, Any]]) -> int | None:
    """判断期望资产是否命中，并返回 1-based rank。

    判断顺序：
    1. 如果配置了 expected_source_ids，就按 source_id 精确判断。
    2. 如果配置了 expected_names，就按 name/display_name/parent_entity_name 判断。
    3. 如果只配置 expected_asset_kind，就按资产类型判断，这种适合早期粗评测。
    """

    expected_source_ids = set(case.expected_source_ids)
    expected_names = set(case.expected_names)

    for index, item in enumerate(items, start=1):
        source_id = str(item.get("source_id") or "")
        candidate_names = {
            str(item.get("name") or ""),
            str(item.get("display_name") or ""),
            str(item.get("parent_entity_name") or ""),
        }
        asset_kind = item.get("asset_kind")

        if expected_source_ids and source_id in expected_source_ids:
            return index

        if expected_names and expected_names.intersection(candidate_names):
            return index

        if (
            not expected_source_ids
            and not expected_names
            and case.expected_asset_kind
            and asset_kind == case.expected_asset_kind
        ):
            return index

    return None


def evaluate_case(*, case: EvalCase, base_url: str, timeout_seconds: int) -> EvalResult:
    """执行单条评测样例。"""

    try:
        response_data = call_search_api(
            base_url=base_url,
            query=case.query,
            limit=case.limit,
            timeout_seconds=timeout_seconds,
        )
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return EvalResult(
            case=case,
            hit_rank=None,
            returned_count=0,
            top_items=[],
            error=str(exc),
        )

    items = response_data.get("items") or []
    hit_rank = find_hit_rank(case, items)
    return EvalResult(
        case=case,
        hit_rank=hit_rank,
        returned_count=len(items),
        top_items=items[: min(3, len(items))],
    )


def print_result(result: EvalResult) -> None:
    """打印单条样例的结果，方便人工快速看问题。"""

    status = "PASS" if result.hit else "FAIL"
    if result.error:
        status = "ERROR"

    print(f"[{status}] {result.case.id} query={result.case.query!r}")
    if result.error:
        print(f"  error: {result.error}")
        return

    print(f"  returned={result.returned_count}, hit_rank={result.hit_rank}")
    for rank, item in enumerate(result.top_items, start=1):
        print(
            "  "
            f"top{rank}: "
            f"source_table={item.get('source_table')} "
            f"source_id={item.get('source_id')} "
            f"asset_kind={item.get('asset_kind')} "
            f"name={item.get('name')} "
            f"score={item.get('score')}"
        )


def print_summary(results: list[EvalResult]) -> None:
    """打印整体指标。

    Hit@K：期望目标是否出现在本次返回结果里。
    MRR：命中排名越靠前越高，top1 命中为 1.0，top2 命中为 0.5。
    """

    total = len(results)
    if total == 0:
        print("No eval cases found.")
        return

    error_count = sum(1 for item in results if item.error)
    hit_count = sum(1 for item in results if item.hit)
    mrr = sum(item.reciprocal_rank for item in results) / total

    print()
    print("=== Summary ===")
    print(f"total={total}")
    print(f"errors={error_count}")
    print(f"hit_rate={hit_count / total:.2%}")
    print(f"mrr={mrr:.4f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate asset semantic search quality.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="FastAPI 服务地址，例如 http://127.0.0.1:8000 或 http://124.174.8.150:8000",
    )
    parser.add_argument(
        "--eval-file",
        default=str(DEFAULT_EVAL_FILE),
        help="JSONL 评测文件路径",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="单次接口请求超时时间，单位秒",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    eval_file = Path(args.eval_file)
    cases = load_eval_cases(eval_file)

    results = [
        evaluate_case(
            case=case,
            base_url=args.base_url,
            timeout_seconds=args.timeout,
        )
        for case in cases
    ]

    for result in results:
        print_result(result)

    print_summary(results)


if __name__ == "__main__":
    main()
