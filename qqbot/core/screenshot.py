"""QQBot 的动态截图服务客户端。"""

import os

import httpx


async def fetch_dynamic_screenshot(
    dynamic_id: str, remote_url: str | None = None
) -> bytes:
    """从独立截图服务获取动态卡片 PNG。"""
    url = remote_url if remote_url is not None else os.getenv("BILI_SCREENSHOT_URL", "")
    if not url:
        raise RuntimeError(
            "未配置截图服务地址（传入 remote_url 或设置 BILI_SCREENSHOT_URL）"
        )
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(url, json={"dynamic_id": dynamic_id})
        response.raise_for_status()
        return response.content
