from .base import BaseMusicPlayer
from .ncm import NetEaseMusic
from .ncm_nodejs import NetEaseMusicNodeJS
from .spotify import SpotifyMusic
from .txqq import TXQQMusic

__all__ = [
    "NetEaseMusic",
    "NetEaseMusicNodeJS",
    "SpotifyMusic",
    "BaseMusicPlayer",
    "TXQQMusic",
]

