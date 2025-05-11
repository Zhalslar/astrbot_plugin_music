import httpx
import random


class DataApi:
    """
    从网易云音乐接口直接获取数据（实验性）
    """

    headers = {"referer": "http://music.163.com"}
    cookies = {"appver": "2.0.2"}

    async def search(self, song_name: str):
        """
        搜索接口，用于由歌曲名查找id
        """
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "http://music.163.com/api/search/get/web",
                data={"s": song_name, "limit": 5, "type": 1, "offset": 0},
                headers=self.headers,
                cookies=self.cookies,
            )
        jsonified_r = r.json()
        if "result" not in jsonified_r:
            raise APINotWorkingException(r.text)
        return jsonified_r

    async def getHotComments(self, song_id: int):
        """
        获取热评
        """
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://music.163.com/weapi/v1/resource/hotcomments/R_SO_4_{song_id}?csrf_token=",
                data={
                    # 不知道从哪毛来的key
                    "params": "D33zyir4L/58v1qGPcIPjSee79KCzxBIBy507IYDB8EL7jEnp41aDIqpHBhowfQ6iT1Xoka8jD+0p44nRKNKUA0dv+n5RWPOO57dZLVrd+T1J/sNrTdzUhdHhoKRIgegVcXYjYu+CshdtCBe6WEJozBRlaHyLeJtGrABfMOEb4PqgI3h/uELC82S05NtewlbLZ3TOR/TIIhNV6hVTtqHDVHjkekrvEmJzT5pk1UY6r0=",
                    "encSecKey": "45c8bcb07e69c6b545d3045559bd300db897509b8720ee2b45a72bf2d3b216ddc77fb10daec4ca54b466f2da1ffac1e67e245fea9d842589dc402b92b262d3495b12165a721aed880bf09a0a99ff94c959d04e49085dc21c78bbbe8e3331827c0ef0035519e89f097511065643120cbc478f9c0af96400ba4649265781fc9079",
                },
                headers=self.headers,
                cookies=self.cookies,
            )
        jsonified_r = r.json()
        if "hotComments" not in jsonified_r:
            raise APINotWorkingException(r.text)
        return jsonified_r

    async def getSongInfo(self, song_id: int):
        """
        获取歌曲信息
        """
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"http://music.163.com/api/song/detail/?id={song_id}&ids=%5B{song_id}%5D",
            )
        jsonified_r = r.json()
        if "songs" not in jsonified_r:
            raise APINotWorkingException(r.text)
        return jsonified_r


class DataGet(DataApi):
    """
    从dataApi获取数据，并做简单处理
    """

    api = DataApi()

    async def song_ids(self, song_name: str, amount=5) -> list:
        """
        根据用户输入的songName 获取候选songId列表 [默认songId数量：5]
        """
        song_ids = []
        r = await self.api.search(song_name=song_name)
        id_range = (
            amount if amount < len(r["result"]["songs"]) else len(r["result"]["songs"])
        )
        for i in range(id_range):
            song_ids.append(r["result"]["songs"][i]["id"])
        return song_ids

    import random

    async def song_comments(self, song_id: int, amount=5) -> str:
        """
        根据传递的单一song_id，随机获取一条热评内容
        """
        r = await self.api.getHotComments(song_id)
        # 确保评论数量不超过amount
        comments = r["hotComments"][:amount]
        # 随机选择一条评论并返回其内容
        if comments:  # 确保列表不为空
            return random.choice(comments)["content"]
        else:
            # 如果没有评论，返回一个空字符串或者可以选择抛出异常
            return "好听的"

    async def song_info(self, song_id: int) -> dict:
        """
        根据传递的songId，获取歌曲名、歌手、专辑等信息，作为dict返回
        """
        song_info = {}
        r = await self.api.getSongInfo(song_id)
        song_info["songName"] = r["songs"][0]["name"]
        song_artists = []
        for ars in r["songs"][0]["artists"]:
            song_artists.append(ars["name"])
        song_artists_str = "、".join(song_artists)
        song_info["songArtists"] = song_artists_str

        song_info["songAlbum"] = r["songs"][0]["album"]["name"]

        return song_info


class DataProcess:
    """
    将获取的数据处理为用户能看懂的形式
    """

    @staticmethod
    async def mergeSongInfo(song_infos: list) -> str:
        """
        将歌曲信息list处理为字符串，供用户点歌
        传递进的歌曲信息list含有多个歌曲信息dict
        """
        song_info_message = "发送【序号】选歌喵(默认0)：\n"
        num_id = 0
        for song_info in song_infos:
            song_info_message += f"{num_id}："
            song_info_message += song_info["songName"]
            song_info_message += "-"
            song_info_message += song_info["songArtists"]
            # song_info_message += " 专辑："
            # song_info_message += song_info["songAlbum"]
            if num_id < len(song_infos) - 1:
                song_info_message += "\n"
            num_id += 1
        return song_info_message

    @staticmethod
    async def mergeSongComments(song_comments: dict) -> str:
        song_comments_message = "\n".join(
            ["%s： %s" % (key, value) for (key, value) in song_comments.items()]
        )
        return song_comments_message


class APINotWorkingException(Exception):
    def __init__(self, wrongData):
        self.uniExceptionTip = "网易云音乐接口返回了意料之外的数据：\n"
        self.wrongData = wrongData

    def __str__(self):
        return self.uniExceptionTip + self.wrongData
