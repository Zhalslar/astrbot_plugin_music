<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_music?name=astrbot_plugin_music&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_music

_🎵 高性能多平台点歌插件 🎵_

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-Zhalslar-blue)](https://github.com/Zhalslar)

</div>

---

## 🤝 插件介绍

`astrbot_plugin_music` 是一个 **高内聚、低耦合、可扩展** 的点歌插件，核心特性如下：

- 🎧 多平台统一抽象（BaseMusicPlayer）
- 🔁 多发送方式自动降级
- 📃 文本 / 图片 / 单曲 三种选歌模式
- 💬 支持歌词、热评、卡片、语音、文件
- 📂 用户独立歌单（本地持久化）
- 🤖 支持 LLM Tool 自动点歌
- 🚫 无需 VIP，不绑定单一平台

---

## 📦 安装

在 AstrBot 插件市场搜索 **astrbot_plugin_music**，点击安装并启用。

---

## ⚙️ 配置说明

请前往 **AstrBot 插件配置面板**进行设置。

### 🎼 默认点歌平台

**default_player_name**

- 定义 `点歌` 命令默认使用的平台
- 所有平台均可通过命令显式调用

支持平台（部分）：

- 网易点歌 / nj点歌（NodeJS）
- QQ 点歌
- 酷狗 / 酷我
- 百度 / 咪咕
- 荔枝 / 蜻蜓 / 喜马拉雅
- 5sing 原创 / 翻唱
- 全民 K 歌

---

### 🔍 搜索与选择

**song_limit**

- 搜索返回歌曲数量
- 当选择模式为 `single` 时强制为 1

**select_mode**

| 模式   | 行为                     |
| ------ | ------------------------ |
| text   | 文本列表，等待输入序号   |
| image  | 图片列表（依赖下游 t2i） |
| single | 自动选中第一首           |

---

### 📤 发送策略（核心）

**send_modes**

定义歌曲发送方式的优先级，失败自动降级：

1. card（卡片，仅 QQ + 网易云）
2. record（语音）
3. file（文件）
4. text（文本链接）
5. 点歌列表 `<序号> <模式>` | 播放歌单歌曲，模式：卡片/语音/文件/文本 或者 1/2/3/4

> 排在前面的方式优先，发送失败将自动尝试下一种。

---

### 🧩 附加功能

| 配置项          | 说明               |
| --------------- | ------------------ |
| enable_comments | 发送后附加热评     |
| enable_lyrics   | 发送歌词图片       |
| timeout         | 选歌等待超时（秒） |
| clear_cache     | 重载插件时清空缓存 |
| proxy           | 网络代理地址       |

---

## ⌨️ 使用说明

### 🎶 点歌

| 命令                  | 说明             |
| --------------------- | ---------------- |
| 点歌 `<歌名>`         | 使用默认平台点歌 |
| `<平台名>点歌 <歌名>` | 指定平台点歌     |
| 点歌 `<歌名> <序号>`  | 直接选择搜索结果 |
| 查歌词 `<歌名>`       | 查询并发送歌词   |

---

### 📂 歌单功能

| 命令              | 说明         |
| ----------------- | ------------ |
| 歌单收藏 `<歌名>` | 收藏歌曲     |
| 歌单取藏 `<歌名>` | 取消收藏     |
| 歌单列表          | 查看个人歌单 |
| 歌单点歌 `<序号>` | 播放歌单歌曲 |

- 歌单按用户独立存储
- 默认最多 50 首

---

### 🤖 AI 点歌（LLM Tool）

插件提供 LLM Tool：

当用户表达“想听某首歌”时可自动调用播放。

---

## 网易云Nodejs模块说明

> 通过网易云Nodejs项目，使用互联网上公开的项目资源 或 自己部署项目 来获得稳定的网易云音源

>项目地址：[网易云Nodejs项目官网](https://neteasecloudmusicapi.js.org/#/)

- 通过公开的项目获取音源

  如果你不想搭建服务器，又不能使用默认的服务，可以在互联网上搜索`allinurl:eapi_decrypt.html`来寻找公开项目的域名。下面贴一些搜集的公开url。

  ```text
  https://163api.qijieya.cn
  https://zm.armoe.cn
  http://dg-t.cn:3000
  http://111.229.38.178:3333
  https://wyy.xhily.com/
  http://45.152.64.114:3005
  http://42.193.244.179:3000
  https://music-api.focalors.ltd
  ```

  举例：插件的`nodejs_base_url`参数设置为`https://163api.qijieya.cn`，`enable_players`中将`网易云NodeJS版`打勾并调至第一位，即可完成配置。可以多尝试几个域名来寻找稳定音源。
- 部署自己的项目

  通过官网介绍部署项目，获得稳定音源。这里介绍docker compose快速部署。

  修改`astrbot.yml`文件，添加服务

  ```yaml
    netease_cloud_music_api:
      image: binaryify/netease_cloud_music_api
      container_name: netease_cloud_music_api
      environment:
        - http_proxy=
        - https_proxy=
        - no_proxy=
        - HTTP_PROXY=
        - HTTPS_PROXY=
        - NO_PROXY=
      networks:
        - astrbot_network
      # ports:
      #   - "3000:3000" 可以通过公共端口来调试
  ```

  然后在`astrbot.yml`文件所在的目录运行命令启动服务：

  ```cmd
  docker compose -f astrbot.yml up -d netease_cloud_music_api
  ```

  如果你开放了上面的调试端口，可以通过`{主机名}:3000`访问示例页面

  将参数`enable_players`中将`网易云NodeJS版`打勾并调至第一位，即可完成配置。

  这里的端口号3000可以修改成其他端口，具体见 Nodejs项目 文档。

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 想第一时间得到反馈的可以来作者的插件反馈群（QQ群）：460973561（不点star不给进）

## ❤️ Contributors

<a href="https://github.com/Zhalslar/astrbot_plugin_music/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Zhalslar/astrbot_plugin_music" />
</a>
