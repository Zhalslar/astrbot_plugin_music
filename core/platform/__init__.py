from .base import BaseMusicPlayer
from .ncm import NetEaseMusic
from .ncm_nodejs import NetEaseMusicNodeJS
from .qqmusic import QQMusicOfficial
from .txqq import TXQQMusic

__all__ = [
    "NetEaseMusic",
    "NetEaseMusicNodeJS",
    "BaseMusicPlayer",
    "TXQQMusic",
    "QQMusicOfficial",
]
