import re
from enum import IntEnum

from .model import Song


class SendMode(IntEnum):
    """Song send modes."""

    CARD = 1
    RECORD_LINK = 2
    RECORD_LOCAL = 3
    FILE_LINK = 4
    FILE_LOCAL = 5
    TEXT = 6


# Mode alias map.
MODE_MAP_CN: dict[str, SendMode] = {
    "卡片": SendMode.CARD,
    "语音": SendMode.RECORD_LOCAL,
    "语音链接": SendMode.RECORD_LINK,
    "本地语音": SendMode.RECORD_LOCAL,
    "文件": SendMode.FILE_LOCAL,
    "文件链接": SendMode.FILE_LINK,
    "本地文件": SendMode.FILE_LOCAL,
    "文本": SendMode.TEXT,
    "card": SendMode.CARD,
    "record": SendMode.RECORD_LOCAL,
    "record_link": SendMode.RECORD_LINK,
    "record_local": SendMode.RECORD_LOCAL,
    "file": SendMode.FILE_LOCAL,
    "file_link": SendMode.FILE_LINK,
    "file_local": SendMode.FILE_LOCAL,
    "text": SendMode.TEXT,
}


def pick_best_song(query: str, songs: list[Song]) -> Song | None:
    """Select the candidate that best matches a song title and singer query.

    Args:
        query: User-provided song title and optional singer.
        songs: Search results to rank.

    Returns:
        The best matching song, the first result when no match scores, or None
        when the result list is empty.
    """
    if not songs:
        return None

    normalized_query = (
        re.sub(r"[\s\-—_/、,，.。:：;；·|]+", " ", query.strip()).strip().lower()
    )
    if not normalized_query:
        return songs[0]

    tokens = [token for token in normalized_query.split(" ") if len(token) >= 2]

    def score_song(song: Song) -> float:
        name = (song.name or song.title or "").strip().lower()
        singer = (song.artists or song.author or "").strip().lower()
        singers = [part.strip() for part in singer.split("/") if part.strip()]
        score = 0.0
        if name and name in normalized_query:
            score += 2.0
        for token in tokens:
            if name and token in name:
                score += 1.5
            if singer and token in singer:
                score += 1.5
        if (
            name
            and name in normalized_query
            and any(singer_name in normalized_query for singer_name in singers)
        ):
            score += 3.0
        return score

    best_song = max(songs, key=score_song)
    return best_song if score_song(best_song) > 0 else songs[0]


def parse_user_input(arg: str) -> tuple[int, list[str] | None, str | None]:
    """Parse the selected song input format.

    Args:
        arg: Raw user input after the song name.

    Returns:
        A tuple containing the selected index, the chosen send modes, and an
        optional parsing error message.
    """
    parts = arg.split()
    index = 0
    way = None
    modes = None
    mode_map = {
        SendMode.CARD: ["card"],
        SendMode.RECORD_LINK: ["record_link"],
        SendMode.RECORD_LOCAL: ["record_local"],
        SendMode.FILE_LINK: ["file_link"],
        SendMode.FILE_LOCAL: ["file_local"],
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
            if 1 <= mode_value <= 6:
                way = SendMode(mode_value)
            else:
                return (
                    0,
                    None,
                    "模式数字应为 1-6：1卡片 2语音链接 3本地语音 4文件链接 5本地文件 6文本",
                )
        else:
            # 尝试匹配文本模式
            way = MODE_MAP_CN.get(second_part)
            if way is None:
                return (
                    0,
                    None,
                    "未知模式「"
                    f"{second_part}」，可用模式：卡片/语音/语音链接/本地语音/文件/文件链接/本地文件/文本 "
                    "或 1/2/3/4/5/6",
                )
    modes = mode_map.get(way) if way else None
    return index, modes, None
