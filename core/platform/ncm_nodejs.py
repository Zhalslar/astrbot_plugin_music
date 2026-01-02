import aiohttp

from .base import BaseHttpPlatform


class NetEaseMusicNodeJS(BaseHttpPlatform):
    """
    网易云音乐 NodeJS API
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config["base_url"]
        self.session = aiohttp.ClientSession()

    async def fetch_data(self, keyword: str, limit=5):
        result = await self._request(
            url=f"{self.base_url}/search",
            method="POST",
            data={"keywords": keyword, "limit": limit, "type": 1, "offset": 0},
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
        result = await self._request(
            url=f"{self.base_url}/comment/hot",
            method="POST",
            data={"id": song_id, "type": 0},
        )
        return result.get("hotComments", [])

    async def fetch_lyrics(self, song_id: int):
        result = await self._request(f"/lyric?id={song_id}")
        return result.get("lrc", {}).get("lyric", "歌词未找到")

    async def fetch_extra(self, song_id: int):
        result = await self._request(
            url=f"{self.base_url}/song/url",
            method="POST",
            data={"id": song_id},
        )
        return {"audio_url": result["data"][0].get("url", "")}
