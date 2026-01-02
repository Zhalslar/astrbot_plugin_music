import aiohttp

from astrbot.api import logger


class SearcherMusic:
    """
    用于从指定音乐平台搜索歌曲信息的工具类。

    支持的平台：
    - qq: QQ 音乐
    - netease: 网易云音乐
    - kugou: 酷狗音乐
    - kuwo: 酷我音乐
    - baidu: 百度音乐
    - 1ting: 一听音乐
    - migu: 咪咕音乐
    - lizhi: 荔枝FM
    - qingting: 蜻蜓FM
    - ximalaya: 喜马拉雅
    - 5singyc: 5sing原创
    - 5singfc: 5sing翻唱
    - kg: 全民K歌

    支持的过滤条件：
    - name: 按歌曲名称搜索（默认）
    - id: 按歌曲 ID 搜索
    - url: 按音乐地址（URL）搜索
    """

    def __init__(self):
        """初始化请求 URL 和请求头"""
        self.base_url = "https://music.txqq.pro/"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        self.session = aiohttp.ClientSession()

    async def fetch_data(self, song_name: str, platform_type: str, limit: int = 5):
        """
        向音乐接口发送 POST 请求以获取歌曲数据

        :param song_name: 要搜索的歌曲名称
        :param platform_type: 音乐平台类型，如 'qq', 'netease' 等
        :return: 返回解析后的 JSON 数据或 None
        """
        data = {
            "input": song_name,
            "filter": "name",  # 当前固定为按名称搜索
            "type": platform_type,
            "page": 1,
        }

        try:
            async with self.session.post(
                self.base_url, data=data, headers=self.headers
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return [
                        {
                            "id": song["songid"],
                            "name": song.get("title", "未知"),
                            "artists": song.get("author", "未知"),
                            "url": song.get("url", "无"),
                            "link": song.get("link", "无"),
                            "lyrics": song.get("lrc", "无"),
                            "cover_url": song.get("pic", "无"),
                        }
                        for song in result["songs"][:limit]
                    ]
                else:
                    logger.error(f"请求失败:{response.status}")
                    return None
        except Exception as e:
            logger.error(f"请求异常: {e}")
            return None

    # TODO: 完善

    async def close(self):
        await self.session.close()
