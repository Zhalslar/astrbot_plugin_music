from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from .data_source import DataGet, DataProcess

dataGet = DataGet()


@register(
    "astrbot_plugin_music",
    "Zhalslar",
    "音乐搜索、热评",
    "1.0.0",
    "https://github.com/Zhalslar/astrbot_plugin_music",
)
class MusicPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("点歌")
    async def get_song(self, event: AstrMessageEvent):
        # 获取歌名,去除命令头“点歌”
        song_name = event.message_str.replace("点歌", "")

        song_ids = await dataGet.song_ids(song_name=song_name)

        if not song_ids:
            yield event.plain_result("没能找到这首歌喵~")

        # 获取歌曲信息列表
        # song_infos = []
        # for song_id in song_ids:
        #     song_info = await dataGet.song_info(song_id=song_id)
        #     song_infos.append(song_info)

        # # 合并歌曲信息
        # song_infos = await DataProcess.mergeSongInfo(song_infos=song_infos)
        # # 如果用户没有选择，发送歌曲信息列表供用户选择
        # yield event.plain_result(song_infos)

        # 获取用户选择的歌曲ID
        selected_song_id = song_ids[0]

        # 发送歌曲
        if event.get_platform_name() == "aiocqhttp":
            # qq
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            payloads = {
                "group_id": int(event.get_group_id()),
                "message": [
                    {
                        "type": "music",
                        "data": {
                            "type": "163",
                            "id": str(selected_song_id),
                        },
                    }
                ],
            }
            await client.api.call_action("send_group_msg", **payloads)


        # 评论歌曲
        song_comments = await dataGet.song_comments(song_id=selected_song_id)
        yield event.plain_result(song_comments)
