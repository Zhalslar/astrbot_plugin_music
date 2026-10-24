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

在 AstrBot 插件市场搜索 **astrbot_plugin_music**，点击安装即可。

---

## 效果展示图

<img width="100%" alt="music插件展示" src="https://github.com/user-attachments/assets/a90683ec-4107-4882-91ff-a2a318c5f0a1" />


---

## ⚙️ 配置说明

请前往 **AstrBot 插件配置面板** 设置。一般只需添加并启用音源、设置默认音源，再按需调整选歌和发送方式。

| 分类 | 配置项 | 说明 |
| ---- | ------ | ---- |
| 搜歌 | 默认音源 | 未指定平台时使用，需选择已添加并启用的音源。 |
| 搜歌 | 搜索歌曲数量限制 | 每次搜索的候选数量；使用单曲模式时自动只取 1 首。 |
| 搜歌 | 选择模式 | 按顺序尝试 **按钮 / 文本 / 图片 / 单曲** 模式，当前方式失败时使用下一种。单曲模式会直接选第一首，建议放在首位。 |
| 搜歌 | 候选菜单 | 可设置图片模式的每行列数、等待选歌的超时时长，以及点歌成功后是否撤回候选消息。 |
| 音源 | 启用与触发词 | 每个音源可单独启用，并配置多个点歌触发词。 |
| 音源 | 内置平台 | 支持网易云 Web API、网易云 NodeJS API、Neko 云音乐、QQ 音乐、TXQQ 聚合音源和 Apple Music。Apple Music 通常只提供约 30 秒官方试听片段。 |
| 音源 | TXQQ 聚合音源 | 触发词可写为 `触发词:子音源标识`，例如 `一听音乐:1ting`；未指定时使用默认子音源。 |
| 音源 | 连接参数 | 各音源可单独设置代理；网易云 NodeJS 和 Neko 可设置 API 根地址；QQ 音乐需填写绑定 QQ 号（UIN），Cookies 按需填写。 |
| 发歌 | 发送模式 | 按优先级排列 **卡片 / 签名卡片 / 语音链接 / 本地语音 / 文件链接 / 本地文件 / 文本**，发送失败时自动尝试下一种。 |
| 发歌 | 签名卡片 API key | 使用签名卡片时必填。在 [apii.xianyuw.cn](https://apii.xianyuw.cn) 注册后，从用户中心复制 API 令牌。 |
| 发歌 | 平台兼容性 | 可填写不支持发语音或文件的 AstrBot 消息平台名称，以跳过对应发送方式。 |
| 附加 | 热评、歌词图片、LLM 回传 | 可在发歌成功后附加热评或歌词图片；没有可用热评时，可将点歌结果返回给 LLM 触发回复。 |

---

## ⌨️ 使用说明

### 🎶 点歌

| 命令                  | 说明             |
| --------------------- | ---------------- |
| 点歌 `<歌名>`         | 使用默认平台点歌 |
| `<平台名>点歌 <歌名>` | 指定平台点歌     |
| 点歌 `<歌名> <序号>`  | 直接选择搜索结果 |
| 查歌词 `<歌名>`       | 查询并发送歌词   |
| `<歌曲列表序号> <模式>` | 播放歌单歌曲，模式：卡片/语音/语音链接/本地语音/文件/文件链接/本地文件/文本 或者 1/2/3/4/5/6

同时，插件提供 LLM Tool，支持用自然语言点歌、查歌词，当用户表达“想听某首歌”时可自动调用播放。

---

## 网易云Nodejs模块说明

### 自部署网易云Nodejs项目获得网易云音源

- 由于官方已停止维护项目地址：[网易云Nodejs项目官网](https://neteasecloudmusicapi.js.org/#/)

- 如果官方已停止维护，可以尝试用：https://github.com/neteasecloudmusicapienhanced/api-enhanced

### 通过公开的项目获取网易云音源

  如果你不想搭建服务器，又不能使用默认的服务，可以在互联网上搜索`allinurl:eapi_decrypt.html`来寻找公开项目的域名。下面贴一些搜集的公开url。

  ```text
  https://zm.wwoyun.cn
  https://zm.armoe.cn
  http://dg-t.cn:3000
  http://111.229.38.178:3333
  https://wyy.xhily.com/
  http://45.152.64.114:3005
  http://42.193.244.179:3000
  https://music-api.focalors.ltd
  ```

  举例：在 **音乐音源** 中添加 **网易云音乐 NodeJS**，将 **API 根地址** 设置为 `https://zm.wwoyun.cn` 并启用该音源。可以多尝试几个域名来寻找稳定音源。
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

  在 **音乐音源** 中添加 **网易云音乐 NodeJS**，将 **API 根地址** 设置为自建服务地址并启用该音源，即可完成配置。

  这里的端口号3000可以修改成其他端口，具体见 Nodejs项目 文档。

---

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 想第一时间得到反馈的可以来作者的插件反馈群（QQ群）：460973561（不点star不给进）
