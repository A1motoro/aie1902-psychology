"""一次性连通性测试：读取 .env 中 GAD7_*，调用智谱 chat。运行：uv run python scripts/smoke_llm.py"""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.services.ai_client import build_ai_client


async def main() -> None:
    s = get_settings()
    print("ai_backend:", s.ai_backend)
    print("llm_model:", s.llm_model)
    print("llm_base_url:", s.llm_base_url)
    client = build_ai_client(s)
    try:
        text = await client.initial_assistant_content(locale="zh-CN")
        print("initial_assistant_content: OK, length=", len(text))
        print("--- preview ---")
        print(text[:500])
    finally:
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            await aclose()


if __name__ == "__main__":
    asyncio.run(main())
