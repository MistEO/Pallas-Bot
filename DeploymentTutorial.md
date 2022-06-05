# Pallas-Bot的部署简单教程
快来部署属于你自己的牛牛吧(｡･∀･)ﾉﾞ

## 零、看前须知
>你需要一个额外的QQ小号和一台自己的```电脑```或者```服务器```
>
>（请不要用大号进行部署）

欢迎加入牛牛调教群：831322617

## 一、windows系统

(linux系统请看[这里](#二linux系统))

### （一）安装python3*（如果你已经安装过python3的话可以跳过）

可以参考的安装教程https://zhuanlan.zhihu.com/p/43155342
（或者你也可以自行百度其他的安装教程）

>安装python的版本请选择3.x.x

### （二）下载文件

打开pallas的源码仓库[https://github.com/InvoluteHell/Pallas-Bot](https://github.com/InvoluteHell/Pallas-Bot)
> 如果你打不开这个页面，请自行百度解决github打不开的问题

找到```code```这个按钮，选择```Download ZIP```这个按钮，点击就可以下载牛牛的源码了。

~~如果你会用```git```的话就没有看这个教程的必要了,你完全可以试着自己独立完成~~

### （三）配置运行环境
#### 1.解压下载好的并进入根目录
请**务必**将文件后再进行后面的操作

#### 2.用pip安装依赖
这Pallas-Bot的目录打开```命令行窗口```（俗称cmd）

##### 使用以下指令更换pip源为阿里云*（更换为国内源会比默认的国外源快很多)

```cmd 
pip config set global.index-url http://mirrors.aliyun.com/pypi/simple/
```
（或者你也可以百度如何更换为其他的国内源）

*(如果系统无法识别pip指令，请自行百度解决方法。)*

##### 通过手脚架安装nonebot
```cmd
pip install nb-cil
```
详情参见[https://v2.nonebot.dev/docs/start/installation](https://v2.nonebot.dev/docs/start/installation)

##### 在控/制台输入以下内容安装依赖

```cmd
pip install -r requirements.txt
```

(如果这些依赖与其他python程序产生了冲突，请自行百度如何构建python虚拟环境)

#### 3.输入以下指令安装nonebot的apscheduler插件和websockets驱动器

```cmd
nb plugin install nonebot_plugin_apscheduler
nb driver install websockets
```
#### 4.在以下网页查看如何为go-cqhttp配置ffmpeg*（如果不希望牛牛发送语音，可以跳过这一步）

👉[https://docs.go-cqhttp.org/guide/quick_start.html#%E5%AE%89%E8%A3%85-ffmpeg](https://docs.go-cqhttp.org/guide/quick_start.html#%E5%AE%89%E8%A3%85-ffmpeg)

#### 5.安装并启动Mongodb*(这是启动核心功能所必须的)*

参考教程👉https://www.runoob.com/mongodb/mongodb-window-install.html

只需要确认Mongodb启动即可，后面的部分会由Pallas自动完成

### （四）启动Pallas

在项目目录处打开cmd（命令行）窗口输入以下指令

```cmd
nb run
```

### （五）访问后台

一切顺利的话，在加载完后你大概会看到一个显眼链接。把提示的链接复制到浏览器打开（本地部署的话就直接在浏览器访问```http://127.0.0.1:8080/go-cqhttp/```）

### （六）登陆账号

点击左上角```添加账号```的按钮。输入小号的信息，并选择登陆设备类型，并```提交```。不出意外的话部署工作到这里就结束了。

如果登陆失败就换个```设备类型```或是按**提示**进行其他操作

部署过程中的常见问题可以在[群里](#零看前须知)提问

**注意！请不要关闭这个命令行窗口！这会导致Pallas停止运行！**

## 二、Linux系统

（以```ubuntu20.04```为例，其它系统请自行变通）

### 临时获取权限

```bash
sudo su
```

### 安装git

```bash 
apt apt install -y git
```
### clone本仓库

```bash  
git clone https://github.com/InvoluteHell/Pallas-Bot.git
```
### 进入项目目录

```bash
cd Pallas-Bot
```
### 安装python3

```bash
apt install -y python3
```
#### 更换pip源为国内源

```bash
pip config set global.index-url http://mirrors.aliyun.com/pypi/simple/
```

#### 更新pip

```bash
pip install --upgrade pip
```

#### 通过手脚架安装nonebot
```cmd
pip install nb-cil
```
详情参见[https://v2.nonebot.dev/docs/start/installation](https://v2.nonebot.dev/docs/start/installation)

#### 安装依赖

```bash
pip install -r requirements.txt
```

*（与已有环境冲突的话，请自行百度如何用venv创建虚拟环境）*

### 安装ffmpeg*（不需要发语音可以跳过这一步）

```bash
apt install -y ffmpeg
```

### 安装并启动Mongodb

参考教程👉https://www.runoob.com/mongodb/mongodb-linux-install.html

### 安装nonebot的apscheduler插件和websockets驱动器

```bash
nb plugin install nonebot_plugin_apscheduler
nb driver install websockets
```

### 启动Pallas

```bash
nb run
```

(如果8080端口已经被占用，可能会导致启动失败。请在```.env.dev```中更改访问端口

### 访问后台

启动成功后请访问这个地址
```[服务器的ip]:[设定的端口]/go-cqhttp/```

端口默认为```8080```
（如果你打不开这个页面，很有可能是你没有打开对应的防火墙端口）
在此页面设置账号信息即可
