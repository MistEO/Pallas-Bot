# Pallas-Bot 的部署简单教程

快来部署属于你自己的牛牛吧 (｡･∀･)ﾉﾞ

## 看前提示

- 你需要一个额外的 QQ 小号，一台自己的 `电脑` 或 `服务器`，请不要用大号进行部署
- 你自己部署的牛牛与其他牛牛数据并不互通，是一张白纸，需要从头调教

## Windows系统

### 安装 Python3

（如果已经安装过 Python3 的话可以跳过）

参考 [安装教程](https://zhuanlan.zhihu.com/p/43155342)（选择 3.x.x）， 或者你也可以自行搜索其他的安装教程

### 下载源码

1. 打开 Pallas-Bot 的 [源码仓库](https://github.com/InvoluteHell/Pallas-Bot)

2. 找到绿色的 `Code` 按钮，点击 `Download ZIP`

~~如果你会用 `git` 的话就没有看这个教程的必要了，你完全可以试着自己独立完成~~

### 配置 Windows 运行环境

1. 解压下载好的 Pallas-Bot 源码并进入根目录；请**务必**进入文件夹后再进行后面的操作

2. 在 Pallas-Bot 的目录打开 `命令行窗口`（俗称 cmd ）
3. 更换 pip 源为阿里云*（更换为国内源会比默认的国外源快很多）

    ```cmd
    python3 -m pip config set global.index-url http://mirrors.aliyun.com/pypi/simple/
    ```

    或者你也可以搜索如何更换为其他的国内源；如果系统无法识别 `python3` 指令。则需要将 `python3` 添加到环境变量中，具体请自行搜索解决方法。

4. 通过手脚架安装nonebot

    ```cmd
    python3 -m pip install nb-cli
    ```

    详情参见 [安装 NoneBot2](https://v2.nonebot.dev/docs/start/installation)

5. 安装依赖

    ```cmd
    python3 -m pip install -r requirements.txt
    ```

    （如果这些依赖与其他 Python 程序产生了冲突，请自行搜索如何构建python虚拟环境）

6. 安装 nonebot 的 apscheduler 插件和 websockets 驱动器

    ```cmd
    nb plugin install nonebot_plugin_apscheduler
    nb plugin install nonebot_plugin_gocqhttp
    nb driver install websockets
    ```

    （如果你的系统提示找不到 `nb`，请自行尝试添加相关环境变量~）

7. 安装并启动 Mongodb （这是启动核心功能所必须的）

    👉 [Windows 平台安装 MongoDB](https://www.runoob.com/mongodb/mongodb-window-install.html)

    只需要确认 Mongodb 启动即可，后面的部分会由 Pallas-Bot 自动完成

8. 配置 ffmpeg （如果不希望牛牛发送语音，可以跳过这一步）

    👉 [安装 ffmpeg](https://docs.go-cqhttp.org/guide/quick_start.html#%E5%AE%89%E8%A3%85-ffmpeg)

9. 配置文心文生图 key （如果不需要 `牛牛做梦` 功能，可以跳过这一步）

    1. 前往 [文心大模型](https://wenxin.baidu.com/moduleApi/ernieVilg) 申请你的 key
    2. 修改牛牛代码 `src/plugins/dream/__init__.py`，将 `wenxin_ak` 和 `wenxin_sk` 改成你申请到的两个字符串

### 启动 Pallas-Bot

在项目目录处打开 cmd（命令行）窗口输入以下指令

```cmd
nb run
```

**注意！请不要关闭这个命令行窗口！这会导致 Pallas-Bot 停止运行！**

### 访问后台并登陆账号

一切顺利的话，在加载完后你大概会看到一个显眼链接。把提示的链接复制到浏览器打开（本地部署的话就直接在浏览器访问 `http://127.0.0.1:8080/go-cqhttp/` ）；然后就是比较直观的操作了，直接添加你的账号并登陆即可

## Linux系统

（以 `Ubuntu 20.04` 为例，其它系统请自行变通）

### 基本环境配置

```bash
sudo apt update
sudo apt install -y git python3 # 安装 git, python3
sudo ldconfig                   # 更新系统路径
python3 -m pip config set global.index-url http://mirrors.aliyun.com/pypi/simple/ # 更换 pip 源为国内源
python3 -m pip install --upgrade pip # 更新 pip
```

### 配置 Linux 运行环境

1. 安装 nonebot

    ```bash
    python3 -m pip install nb-cli
    ```

    详情参见 [安装 NoneBot2](https://v2.nonebot.dev/docs/start/installation)

2. clone 本仓库并安装项目依赖

    ```bash  
    git clone https://github.com/InvoluteHell/Pallas-Bot.git
    cd Pallas-Bot
    python3 -m pip install -r requirements.txt
    ```

3. 安装 nonebot 的 apscheduler 插件和 websockets 驱动器

    ```bash
    nb plugin install nonebot_plugin_apscheduler
    nb plugin install nonebot_plugin_gocqhttp
    nb driver install websockets
    ```

4. 安装并启动 Mongodb （这是启动核心功能所必须的）

    👉 [Linux 平台安装 MongoDB](https://www.runoob.com/mongodb/mongodb-linux-install.html)

5. 安装 ffmpeg （如果不希望牛牛发送语音，可以跳过这一步）

    ```bash
    sudo apt install -y ffmpeg
    ```

6. 配置文心文生图 key （如果不需要 `牛牛做梦` 功能，可以跳过这一步）

    1. 前往 [文心大模型](https://wenxin.baidu.com/moduleApi/ernieVilg) 申请你的 key
    2. 修改牛牛代码 `src/plugins/dream/__init__.py`，将 `wenxin_ak` 和 `wenxin_sk` 改成你申请到的两个字符串

### 启动 Pallas-Bot 及登陆账号

同上面的 [Windows 教程](#启动-pallas-bot)

## FAQ

### 牛牛只发语音不发文字怎么办？

多半是被腾讯风控了（ WebUI 上点开账号可以看到输出提示），多挂几天就好了 ( ´_ゝ` )

### 突然报错 accounts/binary/accounts.pkl 怎么回事？

<https://github.com/mnixry/nonebot-plugin-gocqhttp/issues/186> 也是插件本身的 bug, 建议自己每次添加/删除账号后，手动备份一下这个文件，如果之前没备份，那就只能删除了这个文件重新配一下账号吧_(:з」∠)_

当然要是有大佬帮忙给插件写个备份机制就更好啦 ✿✿ヽ(°▽°)ノ✿

## 开发者群

QQ 群: [牛牛听话！](https://jq.qq.com/?_wv=1027&k=tlLDuWzc)  
欢迎加入~
