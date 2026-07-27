"""仅供 OneBot/NapCat 使用的原始语音消息段。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OneBotRecord:
    """让 NapCat 直接读取 URL 或共享路径，避免 AstrBot 转为 Base64。

    该类刻意不继承 AstrBot 的 ``Record``。aiocqhttp 适配器会对内置
    ``Record`` 强制下载、转 WAV 并 Base64 编码；普通消息段则会直接使用
    ``toDict`` 的结果。该对象只应在 aiocqhttp 事件中创建。
    """

    file: str

    def toDict(self) -> dict[str, dict[str, str] | str]:
        """返回 OneBot v11 的 record 段，保留原始来源。"""
        return {"type": "record", "data": {"file": self.file}}
