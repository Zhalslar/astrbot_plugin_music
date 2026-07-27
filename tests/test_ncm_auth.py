"""nj 点歌 Cookie 配置行为的回归测试。"""

import json
import sys
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from core.ncm_auth import build_ncm_song_url_request, resolve_ncm_cookie  # noqa: E402


class ResolveNcmCookieTests(unittest.TestCase):
    """验证 template_list 的首项语义和 Cookie 解析结果。"""

    def test_uses_cookie_from_first_template_item_only(self):
        """多个配置项时，只使用第一项，不会读取后续 Cookie。"""
        configs = [
            {
                "__template_key": "ncm",
                "ncm_cookie": "MUSIC_U=first; __csrf=first_csrf",
            },
            {
                "__template_key": "ncm",
                "ncm_cookie": "MUSIC_U=second; __csrf=second_csrf",
            },
        ]

        self.assertEqual(
            resolve_ncm_cookie(configs),
            {"MUSIC_U": "first", "__csrf": "first_csrf"},
        )

    def test_does_not_fall_back_to_later_template_item(self):
        """首项未填 Cookie 时保持匿名，避免隐式选择其他账号。"""
        configs = [
            {"__template_key": "ncm", "ncm_cookie": ""},
            {"__template_key": "ncm", "ncm_cookie": "MUSIC_U=second"},
        ]

        self.assertEqual(resolve_ncm_cookie(configs), {})

    def test_skips_other_song_templates_before_first_nj_template(self):
        """其它点歌模板不能阻止 nj 点歌读取自己的首项配置。"""
        configs = [
            {"__template_key": "future_platform", "token": "unrelated"},
            {"__template_key": "nj", "ncm_cookie": "MUSIC_U=nj_first"},
            {"__template_key": "nj", "ncm_cookie": "MUSIC_U=nj_second"},
        ]

        self.assertEqual(resolve_ncm_cookie(configs), {"MUSIC_U": "nj_first"})

    def test_builds_song_url_without_exposing_cookie_in_query(self):
        """VIP Cookie 必须作为请求 Cookie，而不是 URL 查询参数。"""
        url, cookies = build_ncm_song_url_request(
            "http://ncm-api:3000/",
            2666873333,
            [{"__template_key": "ncm", "ncm_cookie": "MUSIC_U=vip"}],
        )

        self.assertEqual(url, "http://ncm-api:3000/song/url?id=2666873333")
        self.assertNotIn("MUSIC_U", url)
        self.assertEqual(cookies, {"MUSIC_U": "vip"})


class NjConfigSchemaTests(unittest.TestCase):
    """验证点歌专用配置在 WebUI 中可扩展且语义明确。"""

    def test_declares_nj_song_template_in_generic_song_config(self):
        """通用配置容器应以 nj点歌 作为首个可扩展模板。"""
        schema_path = PLUGIN_ROOT / "_conf_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        nj_configs = schema["nj_configs"]
        self.assertEqual(nj_configs["type"], "template_list")
        self.assertEqual(nj_configs["description"], "点歌专用配置")
        self.assertIn("同一类型", nj_configs["hint"])
        self.assertIn("第一项", nj_configs["hint"])
        self.assertEqual(nj_configs["templates"]["nj"]["name"], "nj点歌")
        self.assertIn("ncm_cookie", nj_configs["templates"]["nj"]["items"])


if __name__ == "__main__":
    unittest.main()
