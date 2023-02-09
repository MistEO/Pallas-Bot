# Pallas-Bot 的部署简单教程

快来部署属于你自己的牛牛吧 (｡･∀･)ﾉﾞ

## 看前提示

- 你需要一个额外的 QQ 小号，一台自己的 `电脑` 或 `服务器`，请不要用大号进行部署
- 你自己部署的牛牛与其他牛牛数据并不互通，是一张白纸，需要从头调教
- Pallas-Bot 需要 python 环境为 python3.8 | python3.9 | python3.10
- 提供 `requirements.txt` 文件，可以自行安装依赖，但是推荐使用 poetry 进行依赖管理

## 安装C/C++编译器

本项目用到了`jieba-fast`库，在安装此库时需要C/C++编译器支持，否则会报错

### Linux

#### Centos

```cmd
sudo yum update
sudo yum install gcc-c++
```

#### Ubuntu

```cmd
sudo apt-get update
sudo apt-get install build-essential
```

### Windows

安装[Visual Studio](https://c2rsetup.officeapps.live.com/c2r/downloadVS.aspx?sku=community&channel=Release&version=VS2022&source=VSLandingPage&includeRecommended=true&cid=2030:f2c3856d138a471ca35bf7c62db9ec4d)或者~~更轻量化~~的[Visual Studio 生成工具](https://download.visualstudio.microsoft.com/download/pr/0502e0d3-64a5-4bb8-b049-6bcbea5ed247/d7293c5775ad824c05ee99d071d5262da3e7653d39f3ba8a28fb2917af7c041a/vs_BuildTools.exe)

- 打开下载的exe程序，选择`使用C++的桌面开发`，并在右侧列表选中`MSVC VS 2022 C++ x64/x86 生成工具`，`用于Windows的 C++ CMake 工具`，根据你的系统版本选择`Windows 10 SDK`或者`Windows 11 SDK`其中的一个，然后点击安装，等待安装完成即可

附一张安装VS的图
<img width="214" alt="image" src="https://user-images.githubusercontent.com/109732988/217851134-9cd2b3b5-3da0-4f05-8b7d-3117a5ffe6b0.png">


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

3. 安装 poetry 管理 python 环境

    ```cmd
   python3 -m pip install poetry    
   ```

   如果系统无法识别 `python3` 指令。则需要将 `python3` 添加到环境变量中，具体请自行搜索解决方法。

4. 安装依赖

   ```cmd
   poetry install
   ```

5. 安装并启动 Mongodb （这是启动核心功能所必须的）

    👉 [Windows 平台安装 MongoDB](https://www.runoob.com/mongodb/mongodb-window-install.html)

    只需要确认 Mongodb 启动即可，后面的部分会由 Pallas-Bot 自动完成

6. 配置 ffmpeg （如果不希望牛牛发送语音，可以跳过这一步）

    👉 [安装 ffmpeg](https://docs.go-cqhttp.org/guide/quick_start.html#%E5%AE%89%E8%A3%85-ffmpeg)

### 启动 Pallas-Bot

在项目目录处打开 cmd（命令行）窗口输入以下指令

   ```cmd
   poetry shell
   ```

进入虚拟环境后输入以下指令启动 Pallas-Bot

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
python3 -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ # 更换 pip 源为国内源
python3 -m pip install --upgrade pip # 更新 pip
python3 -m pip install poetry   # 安装 poetry
```

### 配置 Linux 运行环境

1. clone 本仓库并安装项目依赖

    ```bash  
    git clone https://github.com/InvoluteHell/Pallas-Bot.git
    cd Pallas-Bot
    poetry install
    ```

2. 安装并启动 Mongodb （这是启动核心功能所必须的）

    👉 [Linux 平台安装 MongoDB](https://www.runoob.com/mongodb/mongodb-linux-install.html)

3. 安装 ffmpeg （如果不希望牛牛发送语音，可以跳过这一步）

    ```bash
    sudo apt install -y ffmpeg
    ```

### 启动 Pallas-Bot 及登陆账号

同上面的 [Windows 教程](#启动-pallas-bot)

## FAQ

### 牛牛只发语音不发文字怎么办？

多半是被腾讯风控了（ WebUI 上点开账号可以看到输出提示），自己拿手机登下随便找个群发句话，应该会有提示让你验证。如果没有就多挂几天吧，可能过几天就好了 ( ´_ゝ` )

### 使用的是国外的机子怎么办

因为项目默认使用的是国内的 pip 源，所以如果你的机子在国外，那么在安装依赖的时候可能会出现下载失败的情况。

解决方法是在 `pyproject.toml` 中删除以下内容：

```toml
[[tool.poetry.source]]
name = "aliyun"
url = "https://mirrors.aliyun.com/pypi/simple"
default = true
```

然后重新安装依赖即可。

也可以使用如下命令重新导出一份 `requirements.txt` 文件，然后使用国外的源安装依赖：

```bash
poetry export --without-hashes -f requirements.txt --output requirements.txt
```

## 开发者群

QQ 群: [牛牛听话！](https://jq.qq.com/?_wv=1027&k=tlLDuWzc)  
欢迎加入~
