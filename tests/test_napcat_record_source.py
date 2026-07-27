"""NapCat 原始语音来源的零依赖回归测试。"""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN_ROOT = Path(__file__).parents[1]


def load_onebot_record_module():
    """不加载插件其余依赖，单独导入纯消息段定义。"""
    path = PLUGIN_ROOT / "core" / "onebot_record.py"
    spec = importlib.util.spec_from_file_location("onebot_record_for_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_config_module():
    """用最小 AstrBot 桩导入配置模块，验证兼容默认值的读取逻辑。"""
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = types.SimpleNamespace(warning=lambda *_: None)
    core = types.ModuleType("astrbot.core")
    config_package = types.ModuleType("astrbot.core.config")
    astrbot_config = types.ModuleType("astrbot.core.config.astrbot_config")
    astrbot_config.AstrBotConfig = type("AstrBotConfig", (), {})
    star = types.ModuleType("astrbot.core.star")
    context = types.ModuleType("astrbot.core.star.context")
    context.Context = type("Context", (), {})
    utils = types.ModuleType("astrbot.core.utils")
    astrbot_path = types.ModuleType("astrbot.core.utils.astrbot_path")
    astrbot_path.get_astrbot_plugin_data_path = lambda: Path("/tmp")
    astrbot_path.get_astrbot_plugin_path = lambda: Path("/tmp")

    modules = {
        "astrbot": astrbot,
        "astrbot.api": api,
        "astrbot.core": core,
        "astrbot.core.config": config_package,
        "astrbot.core.config.astrbot_config": astrbot_config,
        "astrbot.core.star": star,
        "astrbot.core.star.context": context,
        "astrbot.core.utils": utils,
        "astrbot.core.utils.astrbot_path": astrbot_path,
    }
    path = PLUGIN_ROOT / "core" / "config.py"
    spec = importlib.util.spec_from_file_location("music_config_for_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class OneBotRecordTests(unittest.TestCase):
    def test_preserves_url_as_onebot_record_file(self):
        module = load_onebot_record_module()
        record = module.OneBotRecord("https://example.com/song.mp3")

        self.assertEqual(
            record.toDict(),
            {
                "type": "record",
                "data": {"file": "https://example.com/song.mp3"},
            },
        )

    def test_preserves_shared_local_file_path(self):
        module = load_onebot_record_module()
        path = "/AstrBot/data/plugin_data/astrbot_plugin_music/songs/song.mp3"

        self.assertEqual(module.OneBotRecord(path).toDict()["data"]["file"], path)


class NapCatRecordConfigTests(unittest.TestCase):
    def test_schema_declares_all_record_sources(self):
        schema = json.loads((PLUGIN_ROOT / "_conf_schema.json").read_text())
        setting = schema["napcat_record_source"]

        self.assertEqual(setting["default"], "base64")
        self.assertEqual(setting["options"], ["base64", "url", "local_file"])

    def test_missing_persisted_setting_uses_compatible_default(self):
        module = load_config_module()
        config = object.__new__(module.PluginConfig)
        object.__setattr__(config, "_data", {})

        self.assertEqual(config.napcat_record_source, "base64")

    def test_reads_persisted_record_source_instead_of_class_default(self):
        module = load_config_module()
        config = object.__new__(module.PluginConfig)
        object.__setattr__(config, "_data", {"napcat_record_source": "local_file"})

        self.assertEqual(config.napcat_record_source, "local_file")
