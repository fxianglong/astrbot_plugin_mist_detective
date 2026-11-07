"""开场插画：调用阿里云百炼（DashScope）的通义生图模型（默认 qwen-image）。

没有配置 API Key 时不生成；生成失败只记日志，不影响开局。
接口：异步提交任务 → 轮询任务状态 → 取图片 URL（URL 有效期 24 小时，所以下载到本地再用）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp

from astrbot.api import logger

SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{}"

# 每个题材的画面风格；自定义题材用通用描述
ART = {
    "inn": "中国水墨与工笔结合的插画，大雪封山的古代山间客栈，夜晚，窗内暖黄灯火，屋外风雪，悬疑氛围",
    "shanghai": "1930 年代上海老月份牌与电影海报风格插画，霓虹灯下的舞厅门口，爵士年代，雨夜，悬疑氛围",
    "homestay": "现代写实插画，台风夜的海边民宿，落地窗外狂风暴雨，室内一台还亮着的直播补光灯，悬疑氛围",
    "station": "冷色调科幻概念画，近地轨道空间站内部走廊，冷白灯光，舷窗外是地球，空无一人，悬疑氛围",
    "changan": "唐代风格工笔重彩插画，上元节长安灯会，临街酒楼灯火通明，人潮与花灯，楼上一扇半掩的窗，悬疑氛围",
    "manor": "维多利亚时代油画风格，暴雨夜的英国乡间庄园，书房透出昏黄灯光，老式座钟，悬疑氛围",
    "train": "八十年代怀旧胶片质感插画，大雪中停在山间小站的绿皮火车，车窗透出暖光，站台空旷，悬疑氛围",
    "opera": "江南水乡版画风格，古镇祠堂戏台，后台挂满戏服与面具，昏暗烛光，悬疑氛围",
    "campus": "清新日系动画背景风格，深夜的大学社团活动室，桌上散落的电脑与咖啡杯，窗外校园路灯，悬疑氛围",
    "cyber": "赛博朋克概念画，云层之上的空中都市，霓虹与全息广告，雨夜高楼顶层工作室，悬疑氛围",
}
COMMON = "电影感构图，细节丰富，没有文字，没有水印，没有血腥画面，不出现可辨认的真实人物"


def art_prompt(theme_key: str, setting: str, title: str) -> str:
    style = ART.get(theme_key) or f"精致的悬疑风格插画，场景：{setting[:80]}"
    return f"{style}。主题：{title}。{COMMON}"


class Illustrator:
    def __init__(self, api_key: str, model: str, size: str, out_dir: Path, timeout: int = 120):
        self.api_key = api_key.strip()
        self.model = model.strip() or "qwen-image"
        self.size = size.strip() or "1328*1328"
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def draw(self, prompt: str, name: str) -> str | None:
        """生成一张图，返回本地文件路径；失败返回 None。"""
        if not self.enabled:
            return None
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {"model": self.model, "input": {"prompt": prompt}, "parameters": {"size": self.size, "n": 1, "prompt_extend": True, "watermark": False}}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.post(SUBMIT_URL, json=body, headers={**headers, "X-DashScope-Async": "enable"}) as r:
                    d = await r.json(content_type=None)
                task_id = (d.get("output") or {}).get("task_id")
                if not task_id:
                    logger.warning(f"[侦探社] 插画任务提交失败：{d.get('code')} {d.get('message')}")
                    return None
                url = None
                loop = asyncio.get_running_loop()
                deadline = loop.time() + self.timeout
                while loop.time() < deadline:
                    await asyncio.sleep(3)
                    async with s.get(TASK_URL.format(task_id), headers=headers) as r:
                        d = await r.json(content_type=None)
                    out = d.get("output") or {}
                    st = out.get("task_status")
                    if st == "SUCCEEDED":
                        res = out.get("results") or []
                        url = res[0].get("url") if res else None
                        break
                    if st in ("FAILED", "CANCELED", "UNKNOWN"):
                        logger.warning(f"[侦探社] 插画生成失败：{out.get('code')} {out.get('message')}")
                        return None
                if not url:
                    logger.warning("[侦探社] 插画生成超时")
                    return None
                async with s.get(url) as r:
                    data = await r.read()
            path = self.out_dir / f"{name}.png"
            path.write_bytes(data)
            return str(path)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[侦探社] 插画生成出错：{e}")
            return None
