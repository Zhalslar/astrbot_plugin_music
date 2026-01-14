# typed_config.py
from __future__ import annotations

from typing import Any, get_type_hints

from astrbot.core.config.astrbot_config import AstrBotConfig


class TypedConfigFacade:
    """
    AstrBotConfig 的强类型属性 Facade
    - 不继承
    - 不复制
    - 单一真实状态源
    """

    __annotations__: dict[str, type]

    def __init__(self, cfg: AstrBotConfig):
        object.__setattr__(self, "_cfg", cfg)

        hints = get_type_hints(self.__class__)
        fields = {k: v for k, v in hints.items() if not k.startswith("__")}
        object.__setattr__(self, "_fields", fields)

        # ===== 必填字段校验 =====
        for key in fields:
            if key not in cfg:
                raise KeyError(f"缺少必填配置键: {key}")

        self._preprocess()

    # ---------- dict 行为代理 ----------
    def __getitem__(self, key: str) -> Any:
        return self._cfg[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._cfg[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._cfg

    # ---------- 属性访问 ----------
    def __getattr__(self, key: str) -> Any:
        hints = self.__class__.__annotations__
        if key in hints:
            return self._cfg[key]
        return getattr(self._cfg, key)

    def __setattr__(self, key: str, value: Any) -> None:
        hints = self.__class__.__annotations__
        if key in hints:
            self._cfg[key] = value
        else:
            setattr(self._cfg, key, value)

    # ---------- 生命周期钩子 ----------
    def _preprocess(self) -> None:
        """对配置进行预处理（子类可覆盖）"""
        pass

    # ---------- 保存 ----------
    def save(self) -> None:
        self._cfg.save_config()



class PluginConfig(TypedConfigFacade):
    default_player_name: str
    nodejs_base_url: str
    song_limit: int
    select_mode: str
    send_modes: list[str]
    enable_comments: bool
    enable_lyrics: bool
    proxy: str
    timeout: int
    timeout_recall: bool
    clear_cache: bool
    enc_sec_key: str
    enc_params: str

    def _preprocess(self) -> None:
        self.send_modes = [m.split("(", 1)[0].strip() for m in self.send_modes]
        self.song_limit: int = (
            1 if "single" in self.select_mode else self.song_limit
        )
