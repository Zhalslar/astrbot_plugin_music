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

<img width="8192" height="3342" alt="music插件展示" src="https://github.com/user-attachments/assets/a90683ec-4107-4882-91ff-a2a318c5f0a1" />


## ⚙️ 配置说明

请前往 **AstrBot 插件配置面板**进行设置。

- 发送卡片需要填写配置项**签名卡片 API key**，当前版本使用的站点地址：https://apii.xianyuw.cn，注册后在用户中心复制 API 令牌填写该项插件配置即可。
- 在 **音乐音源** 中添加并启用需要的平台，再按页面说明填写触发词和平台参数。

### 🎼 搜歌配置

在 **搜歌配置** 中可以设置默认音源和候选歌曲的展示方式：

- **默认音源**：用于没有指定平台时的“点歌”命令。可选值是已添加并启用的音源。
- **搜索歌曲数量限制**：每次搜索返回的候选歌曲数量；选择单曲模式时自动只取 1 首。
- **选择模式**：按列表顺序尝试展示候选歌曲，当前方式失败时自动尝试下一种。

| 选择模式 | 行为 |
| -------- | ---- |
| 按钮模式 | 通过 QQ 官方机器人按钮选择 |
| 文本模式 | 发送文本候选列表，等待输入序号 |
| 图片模式 | 渲染本地候选歌曲图片 |
| 单曲模式 | 自动选择第一首；应放在选择模式列表首位 |

**候选菜单的列数**决定图片模式下每行显示的歌曲数量；**选歌等待超时时长（秒）**决定文本或图片列表等待回复的最长时间；**点歌成功后撤回选歌消息**控制发送成功后是否尝试撤回候选列表。

### 🎵 音源设置

在 **音乐音源** 中添加音源后，可通过 **启用此音源** 控制是否参与搜索，通过 **触发词** 设置点歌命令。一个音源可配置多个触发词。

TXQQ 聚合音源的触发词需要同时指定子音源，格式为 `触发词:子音源标识`，例如 `一听音乐:1ting`。未指定子音源时使用 **默认子音源**。

当前内置音源包括：

- 网易云音乐 Web API（网易点歌）
- 网易云音乐 NodeJS API（nj点歌）
- Neko 云音乐 API（Neko点歌）
- QQ 音乐（QQ点歌）
- TXQQ 聚合音源（网易云、QQ、酷狗、酷我、百度、一听、咪咕、荔枝、蜻蜓、喜马拉雅、5sing、全民 K 歌）

各音源可单独设置 **代理地址**；留空时直连。网易云音乐 NodeJS 和 Neko 云音乐还可设置 **API 根地址**。QQ 音乐需要填写 **绑定 QQ 号（UIN）**，也可按需填写 **QQ 音乐 Cookies**。

---

### 📤 发歌配置

在 **发歌配置** 的 **发送模式** 中按优先级排列发送方式；前一种失败时会自动尝试下一种。

| 发送模式 | 说明 |
| -------- | ---- |
| 卡片模式 | 音乐卡片，仅支持 QQ 音乐和网易云音乐音源 |
| 签名卡片 | 通过签名卡片服务发送 |
| 语音链接 | 发送在线语音链接 |
| 本地语音 | 下载后发送语音文件 |
| 文件链接 | 发送音频文件链接 |
| 本地文件 | 下载后发送音频文件 |
| 文本模式 | 发送歌曲信息和音频链接 |

---

### 🧩 附加功能

| 配置项 | 说明 |
| ------ | ---- |
| 发送热评 | 歌曲发送成功后，尝试附加一条热门评论 |
| 发送歌词图片 | 歌曲发送成功后，尝试获取歌词并渲染为图片 |
| 返回点歌结果给 LLM | 没有可用热评时，将发送结果返回给 LLM 以触发回复 |

语音和文件发送方式还可分别配置 **不支持发语音的消息平台** 和 **不支持发文件的消息平台**，填写 AstrBot 消息平台名称以跳过对应方式。

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
