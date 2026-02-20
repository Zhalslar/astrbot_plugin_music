from enum import IntEnum


class SendMode(IntEnum):
    """歌曲发送模式"""

    CARD = 1
    RECORD = 2
    FILE = 3
    TEXT = 4


# 文本模式映射表
MODE_MAP_CN: dict[str, SendMode] = {
    "卡片": SendMode.CARD,
    "语音": SendMode.RECORD,
    "文件": SendMode.FILE,
    "文本": SendMode.TEXT,
    "card": SendMode.CARD,
    "record": SendMode.RECORD,
    "file": SendMode.FILE,
    "text": SendMode.TEXT,
}


def parse_user_input(arg: str) -> tuple[int, list[str] | None, str | None]:
    """解析用户选歌输入格式。

    支持的格式:
        - "2"        → 选择第2首，默认模式
        - "1 2"      → 选择第1首，模式2(语音)
        - "1 卡片"   → 选择第1首，卡片模式
        - "1 record" → 选择第1首，语音模式

    Returns:
        (index, way, error):
            - index: 歌曲序号（0 表示无法解析）
            - way: 发送模式（None 表示使用默认）
            - error: 错误提示（None 表示无错误）
    """
    parts = arg.split()
    index = 0
    way = None
    modes = None
    mode_map = {
        SendMode.CARD: ["card"],
        SendMode.RECORD: ["record"],
        SendMode.FILE: ["file"],
        SendMode.TEXT: ["text"],
    }

    # 情况1: 单个数字 "2"
    if len(parts) == 1 and parts[0].isdigit():
        index = int(parts[0])

    # 情况2: "数字 模式" 格式 "1 2"（数字 数字）
    elif len(parts) == 2 and parts[0].isdigit():
        index = int(parts[0])
        second_part = parts[1]

        # 尝试解析为数字
        if second_part.isdigit():
            mode_value = int(second_part)
            if 1 <= mode_value <= 4:
                way = SendMode(mode_value)
            else:
                return 0, None, "模式数字应为 1-4：1卡片 2语音 3文件 4文本"
        else:
            # 尝试匹配文本模式
            way = MODE_MAP_CN.get(second_part)
            if way is None:
                return (
                    0,
                    None,
                    f"未知模式「{second_part}」，可用模式：卡片/语音/文件/文本 或 1/2/3/4",
                )
    modes = mode_map.get(way) if way else None
    return index, modes, None
