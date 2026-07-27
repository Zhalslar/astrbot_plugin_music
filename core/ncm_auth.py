"""nj 点歌的 NCM Cookie 解析工具。"""

from collections.abc import Mapping
from http.cookies import CookieError, SimpleCookie
from typing import Any
from urllib.parse import urlencode


def resolve_ncm_cookie(configs: Any) -> dict[str, str]:
    """从第一个 nj 点歌模板读取并解析 NCM Cookie。

    点歌专用配置未来可包含不同平台的模板，因此须跳过非 nj 项。多个 nj
    项同时存在时仅使用第一项，避免配置顺序变化时静默切换账号。``ncm``
    是早期模板键，仅为已保存配置保留兼容性。
    """

    if not isinstance(configs, list) or not configs:
        return {}

    first_config = next(
        (
            config
            for config in configs
            if isinstance(config, Mapping)
            and config.get("__template_key") in {"nj", "ncm"}
        ),
        None,
    )
    if first_config is None:
        return {}

    raw_cookie = first_config.get("ncm_cookie")
    if not isinstance(raw_cookie, str) or not raw_cookie.strip():
        return {}

    cookie = SimpleCookie()
    try:
        cookie.load(raw_cookie)
    except CookieError:
        return {}

    return {name: morsel.value for name, morsel in cookie.items()}


def build_ncm_song_url_request(
    api_base_url: str,
    song_id: str | int,
    configs: Any,
) -> tuple[str, dict[str, str]]:
    """构建 nj 点歌的音频地址请求。

    Cookie 交给 HTTP 客户端通过请求头传输，不能拼接到 URL，避免被代理、
    访问日志或异常信息意外记录。
    """

    base_url = str(api_base_url).rstrip("/")
    url = f"{base_url}/song/url?{urlencode({'id': str(song_id)})}"
    return url, resolve_ncm_cookie(configs)
