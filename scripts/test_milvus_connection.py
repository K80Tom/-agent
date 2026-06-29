"""测试 Milvus 连接。"""

from __future__ import annotations

from pathlib import Path
import os
import sys

from dotenv import load_dotenv
from pymilvus import MilvusClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    load_dotenv(override=True)

    client = MilvusClient(
        uri=os.getenv("MILVUS_URI"),
        user=os.getenv("MILVUS_USER"),
        password=os.getenv("MILVUS_PASSWORD"),
    )

    print("Milvus connected")
    print("collections:", client.list_collections())


if __name__ == "__main__":
    main()