from .base import BaseHttpPlatform


class NetEaseMusic(BaseHttpPlatform):
    """
    网易云音乐（Web API）
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookies = {"appver": "2.0.2"}

    async def fetch_data(self, keyword: str, limit=5):
        url = "http://music.163.com/api/search/get/web"
        data = {"s": keyword, "limit": limit, "type": 1, "offset": 0}

        result = await self._request(
            url,
            method="POST",
            data=data,
            cookies=self.cookies,
        )

        return [
            {
                "id": song["id"],
                "name": song["name"],
                "artists": "、".join(a["name"] for a in song["artists"]),
                "duration": song["duration"],
            }
            for song in result["result"]["songs"][:limit]
        ]

    async def fetch_comments(self, song_id: int):
        url = f"https://music.163.com/weapi/v1/resource/hotcomments/R_SO_4_{song_id}?csrf_token="
        data = {
            "params": self.config["enc_params"],
            "encSecKey": self.config["enc_sec_key"],
        }

        result = await self._request(url, method="POST", data=data)
        return result.get("hotComments", [])

    async def fetch_lyrics(self, song_id: int):
        url = f"https://netease-music.api.harisfox.com/lyric?id={song_id}"
        result = await self._request(url)
        return result.get("lrc", {}).get("lyric", "歌词未找到")

    async def fetch_extra(self, song_id: int):
        url = f"https://www.hhlqilongzhu.cn/api/dg_wyymusic.php?id={song_id}&br=7&type=json"
        result = await self._request(url)
        return {
            "title": result.get("title"),
            "author": result.get("singer"),
            "cover_url": result.get("cover"),
            "audio_url": result.get("music_url"),
        }
