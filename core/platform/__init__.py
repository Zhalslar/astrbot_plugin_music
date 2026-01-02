from .base import BaseHttpPlatform, MusicPlatform
from .ncm import NetEaseMusic
from .ncm_nodejs import NetEaseMusicNodeJS

__all__ = ["NetEaseMusic", "NetEaseMusicNodeJS", "BaseHttpPlatform", "MusicPlatform"]


PLATFORM_REGISTRY: dict[str, type[MusicPlatform]] = {
    "netease": NetEaseMusic,
    "netease_nodejs": NetEaseMusicNodeJS,
}


def create_music_platform(config: dict) -> MusicPlatform:
    platform_name = config.get("music_platform")

    if not platform_name:
        raise ValueError("未配置 music_platform")

    platform_cls = PLATFORM_REGISTRY.get(platform_name)
    if not platform_cls:
        raise ValueError(f"不支持的音乐平台: {platform_name}")

    return platform_cls(config)
