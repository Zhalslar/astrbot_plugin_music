"""CZ API 音乐卡片签名发送器

通过 CZ API (api.czcn.xyz) 获取签名 Ark JSON，
再用 OneBot json 消息段发送音乐卡片。

不依赖 NapCat music 消息段，不依赖星之阁签名服务。
"""
import json as _json
from urllib.parse import quote

from astrbot.api import logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .model import Song
from .platform import BaseMusicPlayer, NetEaseMusic, NetEaseMusicNodeJS, TXQQMusic

# CZ API 常量
_CZ_API = "https://api.czcn.xyz/api/qqyykp"

# 平台 → CZ type 参数映射
_FORMAT_MAP = {
    "163": "163",
    "qq": "qq",
    "tx": "qq",
    "tencent": "qq",
    "txqq": "qq",
    "kugou": "kugou",
    "kuwo": "kuwo",
    "migu": "migu",
    "bilibili": "qq",
    "baidu": "qq",
    "mihoyo": "qq",
}


async def send_card_via_cz(
    event: AiocqhttpMessageEvent,
    player: BaseMusicPlayer,
    song: Song,
    ckey: str = "",
) -> bool:
    """通过 CZ API 获取签名 Ark JSON 并发送音乐卡片。

    Args:
        event: 消息事件
        player: 音乐播放器
        song: 歌曲信息
        ckey: CZ API 密钥（可选，提高限额）

    Returns:
        True 表示发送成功
    """
    # 确定平台类型
    is_netease = isinstance(player, (NetEaseMusic, NetEaseMusicNodeJS))
    note = song.note or getattr(player, "_last_platform_type", "qq")
    if isinstance(note, str) and note.startswith("ynx:"):
        note = note.split(":", 1)[1] or "qq"
    if is_netease:
        note = "163"

    # 补全封面与音频直链
    if not song.audio_url or not song.cover_url:
        song = await player.fetch_extra(song)

    audio_url = song.audio_url or ""
    cover = song.cover_url or ""

    if not audio_url:
        logger.error(f"【{song.name}】无音频地址，无法生成卡片")
        return False

    # 封面为空时用默认占位图
    if not cover:
        cover = "https://p.qpic.cn/qqconnect/0/app_100497308_1626060999/100?max-age=2592000&t=0"

    # B 站跳转链接用视频页面
    is_bilibili = note == "bilibili" or (
        hasattr(player, "platform") and player.platform.name == "bilibili"
    )
    if is_bilibili:
        jump_url = f"https://www.bilibili.com/video/{song.id}" if song.id else audio_url
    else:
        jump_url = audio_url

    # 映射平台格式
    fmt = _FORMAT_MAP.get(note, "qq")
    if hasattr(player, "platform"):
        fmt = _FORMAT_MAP.get(player.platform.name, fmt)

    # 构建 CZ API 请求 URL
    api_url = (
        f"{_CZ_API}"
        f"?type={fmt}"
        f"&url={quote(jump_url)}"
        f"&audio={quote(audio_url)}"
        f"&title={quote(song.name or '')}"
        f"&desc={quote(song.artists or '')}"
        f"&image={quote(cover)}"
    )
    if ckey:
        api_url += f"&ckey={quote(ckey)}"

    # 请求 CZ API 签名
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=8, ssl=False) as resp:
                data = await resp.json(content_type=None)

        if isinstance(data, dict) and "app" in data:
            ark_str = _json.dumps(data, ensure_ascii=False)
            payloads = {
                "message": [
                    {"type": "json", "data": {"data": ark_str}}
                ]
            }
            # 用 player 的 session 发送
            if isinstance(event, AiocqhttpMessageEvent):
                if event.is_private_chat():
                    payloads["user_id"] = event.get_sender_id()
                    result = await event.bot.api.call_action("send_private_msg", **payloads)
                else:
                    payloads["group_id"] = event.get_group_id()
                    result = await event.bot.api.call_action("send_group_msg", **payloads)
                if result and result.get("message_id"):
                    logger.debug(f"CZ Ark 卡片发送成功: {song.name}")
                    return True
                logger.warning("CZ Ark 卡片未返回 message_id")
            return False
        else:
            logger.error(f"CZ API 返回异常: {str(data)[:200]}, song={song.name}")
    except Exception as e:
        logger.error(f"CZ Ark 卡片发送失败: {e}")

    return False