# typed_config.py
from __future__ import annotations

import json
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from types import MappingProxyType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import (
    get_astrbot_plugin_path,
    get_astrbot_temp_path,
)


class ConfigNode:
    _SCHEMA_CACHE: dict[type, dict[str, type]] = {}
    _FIELDS_CACHE: dict[type, set[str]] = {}

    @classmethod
    def _schema(cls) -> dict[str, type]:
        return cls._SCHEMA_CACHE.setdefault(cls, get_type_hints(cls))

    @classmethod
    def _fields(cls) -> set[str]:
        return cls._FIELDS_CACHE.setdefault(
            cls,
            {k for k in cls._schema() if not k.startswith("_")},
        )

    @staticmethod
    def _is_optional(tp: type) -> bool:
        if get_origin(tp) in (Union, UnionType):
            return type(None) in get_args(tp)
        return False

    def __init__(self, data: MutableMapping[str, Any]):
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_children", {})
        for key, tp in self._schema().items():
            if key.startswith("_"):
                continue
            if key in data:
                continue
            if hasattr(self.__class__, key):
                continue
            if self._is_optional(tp):
                continue
            logger.warning(f"[config:{self.__class__.__name__}] miss key: {key}")

    def __getattr__(self, key: str) -> Any:
        if key in self._fields():
            value = self._data.get(key)
            tp = self._schema().get(key)

            if isinstance(tp, type) and issubclass(tp, ConfigNode):
                children: dict[str, ConfigNode] = self.__dict__["_children"]
                if key not in children:
                    if not isinstance(value, MutableMapping):
                        raise TypeError(
                            f"[config:{self.__class__.__name__}] "
                            f"key {key} need dict but {type(value).__name__}"
                        )
                    children[key] = tp(value)
                return children[key]

            return value

        if key in self.__dict__:
            return self.__dict__[key]

        raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in self._fields():
            self._data[key] = value
            return
        object.__setattr__(self, key, value)

    def raw_data(self) -> Mapping[str, Any]:
        return MappingProxyType(self._data)

    def save_config(self) -> None:

        if not isinstance(self._data, AstrBotConfig):
            raise RuntimeError(
                f"{self.__class__.__name__}.save_config() only support AstrBotConfig"
            )
        self._data.save_config()


class ConfigNodeContainer:
    """Wrap a template-list configuration as named platform nodes."""

    def __init__(
        self,
        nodes: list[dict[str, Any]],
        item_cls: type[ConfigNode],
        key_name: str = "__template_key",
    ):
        self._nodes: dict[str, ConfigNode] = {}
        for node in nodes:
            key = node.get(key_name)
            if not key:
                logger.warning(f"[music] miss {key_name}, skip platform config")
                continue
            if key in self._nodes:
                logger.warning(f"[music] duplicate platform config: {key}")
            self._nodes[key] = item_cls(node)

    def __getattr__(self, name: str) -> ConfigNode:
        if name in self._nodes:
            return self._nodes[name]
        raise AttributeError(name)

    def __iter__(self):
        return iter(self._nodes.values())

    def keys(self):
        return self._nodes.keys()

    def items(self):
        return self._nodes.items()


class MusicPlayerItem(ConfigNode):
    """Configuration for one music source platform."""

    __template_key: str
    enable: bool
    trigger_words: list[str]
    default_sub_source: str | None
    base_url: str | None
    region: str | None
    uin: str | None
    cookies: str | None
    proxy: str | None
    enc_sec_key: str | None
    enc_params: str | None

    @property
    def name(self) -> str:
        return self._data.get("__template_key", "")


class MusicPlayerConfig(ConfigNodeContainer):
    """Typed collection of configured music source platforms."""

    netease: MusicPlayerItem
    netease_nodejs: MusicPlayerItem
    neko: MusicPlayerItem
    qqmusic: MusicPlayerItem
    txqq: MusicPlayerItem
    apple_music: MusicPlayerItem

    def __init__(self, nodes: list[dict[str, Any]]):
        super().__init__(nodes, item_cls=MusicPlayerItem)

    def platforms(self) -> list[str]:
        return list(self._nodes.keys())

    def enabled_platforms(self) -> list[str]:
        return [name for name, config in self._nodes.items() if config.enable]


class SearchConfig(ConfigNode):
    default_source: str
    song_limit: int
    select_modes: list[str]
    cards_per_row: int
    timeout: int
    recall_select: bool


class SendConfig(ConfigNode):
    send_modes: list[str]
    ark_key: str
    record_unsupported: list[str]
    file_unsupported: list[str]
    enable_comments: bool
    enable_lyrics: bool
    return_play_song_result: bool


class PluginConfig(ConfigNode):
    search_config: SearchConfig
    send_config: SendConfig
    players_template: list[dict[str, Any]]

    _plugin_name: str = "astrbot_plugin_music"

    def __init__(self, config: AstrBotConfig, context: Context):
        super().__init__(config)
        self.context = context
        self.plugin_dir = Path(get_astrbot_plugin_path()) / self._plugin_name
        self.default_template_file = self.plugin_dir / "default_template.json"
        self.font_path = self.plugin_dir / "fonts" / "simhei.ttf"
        self.temp_dir = Path(get_astrbot_temp_path())

        self._select_modes = [
            m.split("(", 1)[0].strip() for m in self.search_config.select_modes
        ]
        self._send_modes = [
            m.split("(", 1)[0].strip() for m in self.send_config.send_modes
        ]
        if not self.players_template:
            try:
                with self.default_template_file.open(encoding="utf-8-sig") as file:
                    self.players_template[:] = json.load(file)
                self.save_config()
            except Exception as exc:
                logger.error(f"[music] failed to load platform template: {exc}")
        self._players = MusicPlayerConfig(self.players_template)

    @property
    def players(self) -> MusicPlayerConfig:
        return self._players

    @property
    def real_select_modes(self) -> list[str]:
        return self._select_modes

    @property
    def real_send_modes(self) -> list[str]:
        return self._send_modes

    @property
    def real_song_limit(self) -> int:
        return (
            1
            if self._select_modes and self._select_modes[0] == "single"
            else self.search_config.song_limit
        )
