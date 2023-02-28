# Pallas-Bot 的部署教程 （AI 篇）

写得很潦草，有空再补充，需要有一定的 python 基础，并且已经安装完了 [部署教程](Deployment.md) 中所需要的环境依赖

我会尽可能保证这篇教程以及最终运行的代码在 CPU 下也能够推理，但为了获得更好的体验和运行速度，还是非常推荐你拥有一块支持 CUDA 的显卡来运行

## Sing

1. 下载 [模型及配置文件](https://huggingface.co/MistEO/Pallas-Bot/tree/main/so-vits-svc/4.0) 放到 `resource/sing/models/XXX/` 文件夹里  

    - 这里的 `XXX` 换成资源文件夹的名字，例如 `pallas`, `amiya` 等，需要对应 `config.json` 里的 `spk` 字段
    - 具体路径结构请参考 [path_structure.txt](https://github.com/MistEO/Pallas-Bot/blob/master/resource/sing/models/path_structure.txt)
    - 在 `src/plugins/sing/__init__.py` 修改 `svc_speakers` 对应上面的资源文件夹名。（也可以在 `.env` 里改）

2. 更新 git 子模块

    ```
    git submodule update --init --recursive
    ```

3. 安装额外依赖，二选一

    - CPU  

        该功能本身约需要 4G 内存，而且比较慢，E3 1230 v2 合成 60 秒音频大概三五分钟（体感，我没具体测）

        ```bash
        python -m pip install -r src/plugins/sing/requirements.txt
        python -m pip install torch torchvision torchaudio
        ```

    - GPU  

        需要 5G 或更高**显存**，否则跑不起来，P106-100 (差不多 GTX1060 的性能）合成 60 秒音频大概需要 30 秒

        ```bash
        python -m pip install -r src/plugins/sing/requirements.txt
        python -m pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu117
        ```

## 画画

敬请期待

## Chat

1. 下载模型，参考 [原仓库说明](https://github.com/BlinkDL/ChatRWKV#%E4%B8%AD%E6%96%87%E6%A8%A1%E5%9E%8B)，把文件放到 `resource/chat/models` 文件夹（只要是 `.pth` 都行，根据你的显存和需求选择）
2. 更新 git 子模块

    ```
    git submodule update --init --recursive
    ```

3. 安装依赖

    - CPU

    ```bash
    python -m pip install torch torchvision torchaudio tokenizers
    ```

    - GPU
    
    ```bash
    python -m pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu117
    python -m pip install tokenizers
    ```

4. `src/plugins/chat/model.py` 里的起手咒语 `init_prompt` 有兴趣可以试着改改

## TTS

**仍在开发中，有能力的可以自己试着先接入玩玩**

1. 下载 [模型资源](https://huggingface.co/MistEO/Pallas-Bot/tree/main/paddlespeech/tts)，放入 `resource/tts/models` 文件夹中
2. 安装依赖

    - GPU 版本（显存占用约 1.5G，合成耗时 1s 左右）  

        因为需要装 cudnn，推荐用 conda 安装。没有 conda 的可以自己去搜教程 cudnn 的安装方法，或者参考 [飞桨官方安装教程](https://www.paddlepaddle.org.cn/documentation/docs/zh/install/pip/linux-pip.html)

        ```bash
        conda install paddlepaddle-gpu==2.4.2 cudatoolkit=11.7 cudnn -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/Paddle/ -c conda-forge
        ```

    - CPU 版本（合成耗时 20s 左右）

        ```
        python3 -m pip install paddlepaddle-gpu==2.4.2.post117 -f https://www.paddlepaddle.org.cn/whl/linux/mkl/avx/stable.html
        ```
