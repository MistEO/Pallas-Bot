# Docker 部署

如果你不想自己配置环境，可以使用 Docker Compose 一键部署已构建好的镜像。镜像中集成了包括  `python`、`ffmpeg` 甚至 `qsign` 等在内的所有环境并经过充分测试，你只需要安装 Docker 和 Docker Compose 即可。目前有基础功能镜像和支持 CPU 版本的所有 AI 功能的镜像，~~GPU 版本的 AI 功能镜像正在测试中~~ GPU 版本经测试不稳定，不过也可以试着部署。

## 准备工作

### 安装 Docker 与 Docker Compose

- [Windows Docker Desktop 安装](https://docs.docker.com/desktop/install/windows-install/) ，推荐使用基于 [WSL 2](https://learn.microsoft.com/zh-cn/windows/wsl/install) 的 Docker CE

- [Linux Docker 安装](https://docs.docker.com/engine/install/ubuntu/)，推荐使用 `curl -sSL https://get.daocloud.io/docker | sh` 命令一键安装

- 安装 [Docker Compose 插件](https://docs.docker.com/compose/install/linux/)，如果你之前已经安装过 Docker，推荐 [单独安装 Docker Compose](https://docs.docker.com/compose/install/other/)。Windows 用户可以直接在 Docker Desktop 中启用 Docker Compose（Settings -> General -> Use Docker Compose V2）。

不要忘了[配置镜像加速](https://www.runoob.com/docker/docker-mirror-acceleration.html)

### 配置 docker-compose.yml

1. 复制一份 [docker-compose.yml](../docker-compose.yml) 文件到本地单独的目录并按需修改 `volumes` 的路径：

    ```yml
    ...
    volumes:
    # 根据需求修改冒号左边路径
    # Windows用户请修改左边为 D:\Pallas-Bot 这样的路径
        - /opt/dockerstore/pallas-bot/resource/:/app/resource
        - /opt/dockerstore/pallas-bot/accounts/:/app/accounts
        - /opt/dockerstore/pallas-bot/.env.prod:/app/.env.prod
    ...
    volumes:
    # 同上
      - /opt/dockerstore/mongo/data:/data/db
      - /opt/dockerstore/mongo/logs:/var/log/mongodb
    ...
    ```

2. 如果你想使用牛牛的 AI 功能（CPU 推理），请为镜像添加标签 `cpuai-latest`：

    ```yml
    ...
      pallasbot:
        container_name: pallasbot
        image: misteo/pallas-bot:cpuai-latest
        restart: always
    ...
    ```

3. 如果你想试着部署支持 GPU 推理的容器，请为镜像添加标签 `gpuai-latest`：

    ```yml
    ...
      pallasbot:
        container_name: pallasbot
        image: misteo/pallas-bot:gpuai-latest
        restart: always
    ...
    ```

    在宿主机上 [安装驱动](https://www.nvidia.com/Download/index.aspx) ，[安装依赖](https://docs.docker.com/config/containers/resource_constraints/#gpu)，并参考 [Docker 官方文档](https://docs.docker.com/compose/gpu-support/) 添加 `deploy` 配置项：

    ```yml
    ...
      volumes:
    ...
      deploy:
        resources:
          reservations:
            devices:
              - driver: nvidia
                device_ids: ['0', '1']
                capabilities: [gpu]
      depends_on:
    ...

    ```

    注意，虽然能够成功启动容器，但是目前 GPU 版本的 AI 功能镜像并不稳定（并且大小达14G以上），可能会出现各种问题。

4. 默认提供的 `docker-compose.yml` 中包含了 `qsign`，你可以根据需要修改 `ANDROID_ID` 和端口等其他参数。推荐在此处使用 `qsign` 而不是自己另外部署，因为你可能会遇到网络等问题。
    > 更新：目前 `8.9.63` 版本的 `qsign` 很容易被风控，可以参考 [这里](https://github.com/rhwong/unidbg-fetch-qsign-onekey)，使用 `dev` 版本的 `go-cqhttp`, `core-1.1.9` 版本的 `qsign` 和 `8.9.68`、`8.9.70` 或 `8.9.71` 版本的 `txlib` 协议（请不要使用 `8.9.73`）。

    ```yml
    ...
      qsign:
        container_name: qsign
        image: xzhouqd/qsign:8.9.63
        environment:
        - PORT=8080
        - COUNT=3
        - ANDROID_ID=114514
        restart: always
    ...
    ```

    注意，此端口不会和 `pallasbot` 容器的端口冲突。

5. 在 docker-compose.yml 所在目录下创建 [.env.prod](../.env.prod) 文件，并根据需要填写相关基础功能参数或 AI 功能参数。具体请参考 [.env](../.env) 文件中的注释。注意，使用 docker-compose 部署时，请将 `MONGO_HOST` 设置为 `mongodb` 容器 的 `service` 名称，如：`MONGO_HOST=mongodb`。

## 启动与登录牛牛

### 启动牛牛

一键启动！

插件形式安装的 Docker Compose 请使用 `docker compose` 代替 `docker-compose`

```bash
# Linux root 用户在 docker-compose.yml 所在目录下执行
docker-compose up -d
# Windows 请使用 powershell 直接执行，无需管理员权限，请不要在 wsl 内执行
```

由于 AI 版镜像较大（CPU 版本需要拉取 4.1G，解压后占空间 9.64G），在此之前也可以先使用 `docker compose pull` 拉取最新镜像。

### 查看日志

通过 `docker-compose logs -f` 查看实时日志，启动完成后就可以访问后台并登陆账号了。若你没有使用 AI 版本镜像，日志中报错未成功加载 `chat` 和 `sing` 插件是正常的，因为基础版镜像未安装相关依赖。

### 登录账号与qsign

请参考 [访问后台并登陆账号](Deployment.md##访问后台并登陆账号)。

记得在配置文件中填写 `sign-server`，并修改 `device.json` 中的 `android_id` 字段为 `qsign` 容器配置的 `ANDROID_ID`。

注意，使用 docker 部署时牛牛的配置文件中应该这样填写 `sign-server`：

```yml
sign-server: 'http://qsign:8080'
```

host 应填写 `qsign` 容器的名称，端口应填写环境变量 `PORT` 所设的端口。

## 后续更新

```bash
# Linux root 用户在 docker-compose.yml 所在目录下执行
docker-compose down     # 停止容器
docker-compose pull     # 拉取最新镜像
docker-compose up -d    # 重新启动容器
# Windows 请使用 powershell 直接执行，无需管理员权限，请不要在 wsl 内执行
```
