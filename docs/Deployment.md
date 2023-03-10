# Pallas-Bot 的部署简单教程

快来部署属于你自己的牛牛吧 (｡･∀･)ﾉﾞ

## 看前提示

- 你需要一个额外的 QQ 小号，一台自己的 `电脑` 或 `服务器`，请不要用大号进行部署
- 你自己部署的牛牛与其他牛牛数据并不互通，是一张白纸，需要从头调教

## Windows系统

### 安装 Python

（如果已经安装过的话可以跳过）

参考 [安装教程](https://zhuanlan.zhihu.com/p/43155342)（推荐 3.8.x 版本）， 或者你也可以自行搜索其他的安装教程

### 配置 Windows 运行环境

1. 下载安装 [git](https://git-scm.com/downloads)
2. 下载源码  
    在你想放数据的文件夹里，Shift + 鼠标右键，打开 Powershell 窗口，clone 牛牛代码

    ```cmd
    git clone https://github.com/MistEO/Pallas-Bot.git --depth=1
    ```

    受限于国内网络环境，请留意命令是否执行成功，若一直失败可以挂上代理

3. 更换 pip 源为阿里云*（更换为国内源会比默认的国外源快很多）

    ```cmd
    python -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
    ```

4. 通过手脚架安装nonebot

    ```cmd
    python -m pip install nb-cli
    ```

    详情参见 [安装 NoneBot2](https://v2.nonebot.dev/docs/start/installation)

5. 安装依赖

    ```cmd
    cd Pallas-Bot # 进入项目目录
    python -m pip install -r requirements.txt
    ```

    （如果这些依赖与其他 Python 程序产生了冲突，推荐使用 miniconda 等虚拟环境）

6. 安装 nonebot 的 apscheduler 插件和 websockets 驱动器

    ```cmd
    nb plugin install nonebot_plugin_apscheduler
    nb plugin install nonebot_plugin_gocqhttp
    nb driver install websockets
    nb driver install fastapi
    ```

    （如果你的系统提示找不到 `nb`，请自行尝试添加相关环境变量~）

7. 安装并启动 Mongodb （这是启动核心功能所必须的）

    👉 [Windows 平台安装 MongoDB](https://www.runoob.com/mongodb/mongodb-window-install.html)

    只需要确认 Mongodb 启动即可，后面的部分会由 Pallas-Bot 自动完成

8. 配置 ffmpeg （如果不希望牛牛发送语音，可以跳过这一步）

    👉 [安装 ffmpeg](https://docs.go-cqhttp.org/guide/quick_start.html#%E5%AE%89%E8%A3%85-ffmpeg)  
    👉 下载 [牛牛语音文件](https://huggingface.co/MistEO/Pallas-Bot/resolve/main/voices/voices.zip)，解压放到 `resource/voices/` 文件夹下（参考 `resource/voices/path_structure.txt`）

### 启动 Pallas-Bot

```cmd
cd Pallas-Bot # 进入项目目录
nb run        # 运行
```

**注意！请不要关闭这个命令行窗口！这会导致 Pallas-Bot 停止运行！**

### 访问后台并登陆账号

一切顺利的话，在加载完后你大概会看到一个显眼链接。把提示的链接复制到浏览器打开（本地部署的话就直接在浏览器访问 `http://127.0.0.1:8080/go-cqhttp/` ）；然后就是比较直观的操作了，直接添加你的账号并登陆即可

### 后续更新

如果牛牛出了新功能你想要使用，同样在项目目录下打开 powershell，执行命令后重新运行牛牛即可

```cmd
git pull origin master
```

### 使用 jieba-fast 分词库

项目默认安装 jieba， 加群较多、需要处理消息量大的用户可以自行安装 jieba-fast，以提升分词速度

```cmd
pip install jieba-fast
```

注：项目将优先尝试导入 jieba-fast 库，如果导入失败则使用 jieba 库, 无需手动修改代码

## Linux系统

（以 `Ubuntu 20.04` 为例，其它系统请自行变通）

### 基本环境配置

```bash
sudo apt update
sudo apt install -y git python # 安装 git, python
sudo ldconfig                   # 更新系统路径
python -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ # 更换 pip 源为国内源
python -m pip install --upgrade pip # 更新 pip
```

### 配置 Linux 运行环境

1. 安装 nonebot

    ```bash
    python -m pip install nb-cli
    ```

    详情参见 [安装 NoneBot2](https://v2.nonebot.dev/docs/start/installation)

2. clone 本仓库并安装项目依赖

    ```bash  
    git clone https://github.com/InvoluteHell/Pallas-Bot.git --depth=1
    cd Pallas-Bot
    python -m pip install -r requirements.txt
    ```

3. 安装 nonebot 的 apscheduler 插件和 websockets 驱动器

    ```bash
    nb plugin install nonebot_plugin_apscheduler
    nb plugin install nonebot_plugin_gocqhttp
    nb driver install websockets
    nb driver install fastapi
    ```

4. 安装并启动 Mongodb （这是启动核心功能所必须的）

    👉 [Linux 平台安装 MongoDB](https://www.runoob.com/mongodb/mongodb-linux-install.html)

5. 安装 ffmpeg （如果不希望牛牛发送语音，可以跳过这一步）

    ```bash
    sudo apt install -y ffmpeg
    sudo ldconfig
    ```
    
    👉 下载 [牛牛语音文件](https://huggingface.co/MistEO/Pallas-Bot/resolve/main/voices/voices.zip)，解压放到 `resource/voices/` 文件夹下（参考 `resource/voices/path_structure.txt`）

### 启动 Pallas-Bot 及登陆账号

同上面的 [Windows 教程](#启动-pallas-bot)

## FAQ

### 牛牛只发语音不发文字怎么办？

多半是被腾讯风控了（ WebUI 上点开账号可以看到输出提示），自己拿手机登下随便找个群发句话，应该会有提示让你验证。如果没有就多挂几天吧，可能过几天就好了 ( ´_ゝ` )

### 唱歌，酒后聊天功能

这些功能对设备性能要求较高，最好有独立显卡，请参考 [部署教程 AI 篇](AIDeployment.md)

## 开发者群

QQ 群: [牛牛听话！](https://jq.qq.com/?_wv=1027&k=tlLDuWzc)  
欢迎加入~
