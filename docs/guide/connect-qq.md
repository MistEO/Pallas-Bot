# 连接 QQ

> **目标**：让 Bot 上线 QQ，群内能收到并回复消息
>
> **准备**：Bot 已运行，能打开 `http://<Bot主机>:8088/pallas/`；一个自备的 OneBot V11 协议端
>
> **完成之后**：协议端账号在线，群里发 **牛牛帮助** 能出图

Pallas-Bot 通过 OneBot V11 反向 WebSocket 接收 QQ 消息。协议端由你自行准备与运维，Pallas 只负责接收连接、显示在线状态并使用该连接收发消息。端口以 `config/pallas.toml` 的 `[bootstrap] port` 为准。

## 连接地址

协议端需要主动连接：

```text
ws://<Bot主机>:8088/onebot/v11/ws
```

- 协议端与 Bot 在同一主机且都不在隔离容器中，可用 `127.0.0.1`。
- 协议端在另一台主机或另一容器中，填写它能访问到的 Bot 地址，不能照抄 `127.0.0.1`。
- 分片部署应连接实际承载账号的 worker 端口，不连接 hub。

## 第 1 步：准备协议端

自选一个兼容 OneBot V11 的协议端，自行部署并遵守它自己的许可证：

- **SnowLuma**：<https://github.com/SnowLuma/SnowLuma>。从 Releases 下载对应平台发行包解压，Windows 跑 `launcher.bat`、Linux 跑 `launcher.sh`，在自带 WebUI 里接入 QQ。其许可为源码可见的非 OSI 许可，商业使用或公开发布修改版、衍生版需事先取得书面授权。
- **NapCat**：<https://github.com/NapNeko/NapCatQQ>，同样以它自己的许可为准。
- Lagrange、LLOneBot 等其它 OneBot V11 实现也可。

Pallas 不提供协议端的安装、托管或容器管理入口，也不随发行包分发协议端。

## 第 2 步：接入反向 WebSocket

1. 在协议端启用反向 WebSocket。
2. URL 填本页开头的 `/onebot/v11/ws` 地址。
3. 启动连接并登录 QQ。

连接成功后，账号会自动出现在 Pallas 控制台首页与 **实例与连接** 中，并标记为“外置账号”。外置账号的安装、升级、扫码和进程生命周期由协议端自己负责；Pallas 只显示连接状态并使用该连接收发消息。

## 验收

把 Bot 拉进测试群并发送：

```text
牛牛帮助
```

收到帮助图即表示 QQ、OneBot V11、Bot 和数据库链路正常。

## 按现象排查

| 现象 | 先检查 |
| --- | --- |
| 外置账号未出现 | 协议端反向 WS URL、网络可达性和协议端日志 |
| 已连接但群里无响应 | 账号是否在群、Bot 日志是否收到事件、插件是否启用 |
| 分片账号离线 | 是否连接了对应 worker，而非 hub |
| 协议端登录失败 | 协议端自身日志、QQ 版本与登录方式 |

下一步：[安装插件](install-plugins.md)。
