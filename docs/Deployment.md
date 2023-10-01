# Pallas-Bot 的部署简单教程

快来部署属于你自己的牛牛吧 (｡･∀･)ﾉﾞ

## 看前提示

- 你需要一个额外的 QQ 小号，一台自己的 `电脑` 或 `服务器`，不推荐用大号进行部署
- 你自己部署的牛牛与其他牛牛数据并不互通，是一张白纸，需要从头调教
- 牛牛支持使用 Docker Compose 一键部署，可以参考 [Docker 部署](DockerDeployment.md)。

## 基本环境配置

1. 下载安装 [git](https://git-scm.com/downloads)，这是一个版本控制工具，可以用来方便的下载、更新牛牛的源码
2. 下载牛牛源码

    在你想放数据的文件夹里，Shift + 鼠标右键，打开 Powershell 窗口，输入命令

    ```bash
    git clone https://github.com/MistEO/Pallas-Bot.git --depth=1
    ```

    受限于国内网络环境，请留意命令是否执行成功，若一直失败可以挂上代理

3. 下载安装 [Python](https://www.python.org/downloads/)，推荐 3.8.x 版本，避免版本不一致带来的不必要麻烦
4. 更换 pip 源为阿里云，并更新 pip

    ```bash
    python -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
    python -m pip install --upgrade pip
    ```

## 项目环境配置

1. 通过手脚架安装 nonebot

    ```bash
    python -m pip install nb-cli
    ```

    详情参见 [安装 NoneBot2](https://v2.nonebot.dev/docs/start/installation)

2. 安装依赖

    ```bash
    cd Pallas-Bot # 进入项目目录
    python -m pip install -r requirements.txt
    ```

    如果这些依赖与其他 Python 程序产生了冲突，推荐使用 miniconda 等虚拟环境

3. 安装 nonebot 的 apscheduler 插件和 websockets 驱动器

    ```bash
    nb plugin install nonebot_plugin_apscheduler
    nb plugin install nonebot_plugin_gocqhttp
    nb driver install websockets
    nb driver install fastapi
    ```

    如果你的系统提示找不到 `nb`，请自行尝试添加相关环境变量~

4. 安装并启动 Mongodb （这是启动核心功能所必须的）

    - [Windows 平台安装 MongoDB](https://www.runoob.com/mongodb/mongodb-window-install.html)
    - [Linux 平台安装 MongoDB](https://www.runoob.com/mongodb/mongodb-linux-install.html)

    只需要确认 Mongodb 启动即可，后面的部分会由 Pallas-Bot 自动完成

5. 配置 FFmpeg （如果不希望牛牛发送语音，可以跳过这一步）

    - [安装 FFmpeg](https://docs.go-cqhttp.org/guide/quick_start.html#%E5%AE%89%E8%A3%85-ffmpeg)
    - 下载 [牛牛语音文件](https://huggingface.co/MistEO/Pallas-Bot/resolve/main/voices/voices.zip)，解压放到 `resource/voices/` 文件夹下，参考 [path_structure.txt](../resource/voices/path_structure.txt)

6. 使用 `jieba-fast` 分词库

    项目默认安装 `jieba`， 加群较多、需要处理消息量大的用户可以自行安装 `jieba-fast`，以提升分词速度（若群较少也可跳过这一步）  

    ```bash
    python -m pip install jieba-fast
    ```

    若安装失败，在 Windows 上可能需要额外安装 `Visual Studio`，Linux 上需要 `build-essential`  
    注：项目将优先尝试导入 `jieba-fast` 库，如果导入失败则使用 `jieba` 库，无需手动修改代码

## 启动 Pallas-Bot

```bash
cd Pallas-Bot # 进入项目目录
nb run        # 运行
```

**注意！请不要关闭这个命令行窗口！这会导致 Pallas-Bot 停止运行！**

## 访问后台并登陆账号

一切顺利的话，在加载完后你大概会看到一个显眼链接，把它复制到浏览器打开  
（本地部署的话可以直接访问 <http://127.0.0.1:8080/go-cqhttp/>）  

然后就是比较直观的操作了，直接添加你的账号并登陆即可  

## 后续更新

如果牛牛出了新功能你想要使用，同样在项目目录下打开 Powershell，执行命令后重新运行牛牛即可

```bash
git pull origin master --autostash
```

## AI 功能

至此，你已经完成了牛牛基础功能的配置，包括复读、轮盘、夺舍、基本的酒后乱讲话等所有非 AI 功能  
（AI 功能目前包括 唱歌、酒后闲聊、酒后 TTS 说话）  

AI 功能均对设备硬件要求较高（要么有一块 6G 显存或更高的英伟达显卡，要么可能占满 CPU 且吃 10G 以上内存）  
若设备性能不足，或对额外的 AI 功能不感兴趣，可以跳过这部分内容。如果每次启动的报错嫌烦，可以直接把对应文件夹删掉，不影响其他功能。  

配置 AI 功能请参考 [部署教程 AI 篇](AIDeployment.md)

## FAQ

### 一直无法登陆

最近腾讯管得严了（所以不要用大号），可以参考 https://github.com/Mrs4s/go-cqhttp/issues/1939 尝试解决下

### 牛牛只发语音不发文字怎么办？

多半是被风控了（ WebUI 上点开账号可以看到输出提示）  
自己拿手机登下随便找个群发句话，应该会有提示让你验证  

如果没有就多挂几天吧，可能过几天就好了 ( ´_ゝ` )

## 开发者群

QQ 群: [牛牛听话！](https://jq.qq.com/?_wv=1027&k=tlLDuWzc)  
欢迎加入~
