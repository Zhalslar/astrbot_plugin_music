from .base import BaseMusicPlayer
from .ncm import NetEaseMusic
from .ncm_nodejs import NetEaseMusicNodeJS
from .neko import NekoMusic
from .qqmusic import QQMusicOfficial
from .txqq import TXQQMusic

__all__ = [
    "BaseMusicPlayer",
    "NekoMusic",
    "NetEaseMusic",
    "NetEaseMusicNodeJS",
    "QQMusicOfficial",
    "TXQQMusic",
]
