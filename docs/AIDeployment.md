# Pallas-Bot 的部署教程 （AI 篇）

配置本教程中的环境前，需要你已经安装完了 [基础教程](Deployment.md) 中所需要的所有环境依赖。  
基础教程已经包括复读、轮盘、夺舍、基本的酒后乱讲话等所有非 AI 功能  
（AI 功能目前包括 唱歌、酒后闲聊、酒后 TTS 说话）

AI 功能均对设备硬件要求较高，且配置操作更加复杂一些。若设备性能不足，或对额外的 AI 功能不感兴趣，可以跳过这部分内容。  
另外以下功能的显存/内存占用，均是且的关系。例如唱歌需要占用 5G 显存，Chat 再选择 6G 的模型，则至少需要 11G 显存才能让两者同时运行起来。  
如果设备性能不足可选择忽略其中某些功能，并删除对应的文件夹，不会影响其他功能（免得每次启动都报错很烦）  

我会尽可能保证这篇教程以及最终运行的代码在 CPU 下也能够推理，但为了获得更好的体验和运行速度，还是非常推荐你拥有一块支持 CUDA 的显卡来运行

## 唱歌（Sing）

1. 下载 [模型及配置文件](https://huggingface.co/MistEO/Pallas-Bot/tree/main/so-vits-svc/4.0) 放到 `resource/sing/models/XXX/` 文件夹里  

    - 这里的 `XXX` 换成资源文件夹的名字，例如 `pallas`, `amiya` 等，需要对应 `config.json` 里的 `spk` 字段
    - 具体路径结构请参考 [path_structure.txt](../resource/sing/models/path_structure.txt)
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

4. （只有一张显卡请忽略这条）若你有多张显卡，可在 `.env` 中添加 `SING_CUDA_DEVICE="1"` （ 1 改成指定设备号）来设置唱歌的 CUDA 设备。

## 酒后聊天（Chat）

1. 下载模型，参考 [原仓库说明](https://github.com/BlinkDL/ChatRWKV#%E4%B8%AD%E6%96%87%E6%A8%A1%E5%9E%8B)；下载 [token 文件](https://github.com/BlinkDL/ChatRWKV/blob/main/20B_tokenizer.json)。都放到 `resource/chat/models` 文件夹（模型只要是 `.pth` 都行，根据你的显存和需求选择）

2. 安装依赖

    - CPU

    ```bash
    python -m pip install torch tokenizers rwkv
    ```

    - GPU
    
    ```bash
    python -m pip install torch --extra-index-url https://download.pytorch.org/whl/cu117
    python -m pip install tokenizers rwkv
    ```

4. `src/plugins/chat/prompt.py` 里的起手咒语 `INIT_PROMPT` 有兴趣可以试着改改
5. `src/plugins/chat/model.py` 里的 `STRATEGY` 可以按上游仓库的 [说明](https://github.com/BlinkDL/ChatRWKV/tree/main#%E4%B8%AD%E6%96%87%E6%A8%A1%E5%9E%8B) 改改，能省点显存啥的

## 酒后语音说话（TTS）

**TTS 所依赖的 [paddlespeech](https://github.com/PaddlePaddle/PaddleSpeech) 目前最新的 1.3.0 版本仅支持到 python 3.9，更高版本的 python 无法支持**

1. 下载 [模型资源](https://huggingface.co/MistEO/Pallas-Bot/tree/main/paddlespeech/tts) common.zip 和 pallas_cn.zip。解压放入 `resource/tts/models` 文件夹中
    - 具体路径结构请参考 [path_structure.txt](../resource/tts/models/path_structure.txt)
    - `vocoder` 下有两个声码器，`pwgan_aishell3` 快，`wavernn_csmsc` 慢很多效果好一点，可以自行选择
2. 安装依赖

    - CPU 版本（合成耗时 20s 左右）

        ```
        python3 -m pip install paddlepaddle-gpu==2.4.2.post117 paddlespeech==1.3.0 -f https://www.paddlepaddle.org.cn/whl/linux/mkl/avx/stable.html
        ```

    - GPU 版本（显存占用约 1.5G，合成耗时 1s 左右）  

        因为需要装 cudnn，推荐用 conda 安装。没有 conda 的可以自己去搜教程 cudnn 的安装方法，或者参考 [飞桨官方安装教程](https://www.paddlepaddle.org.cn/documentation/docs/zh/install/pip/linux-pip.html)

        ```bash
        conda install paddlepaddle-gpu==2.4.2 paddlespeech==1.3.0 cudatoolkit=11.7 cudnn -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/Paddle/ -c conda-forge
        ```

## 画画

敬请期待
