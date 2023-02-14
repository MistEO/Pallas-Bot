# Pallas-Bot 的部署教程 （AI 篇）

写得很潦草，有空再补充，需要有一定的 python 基础，并且已经安装完了 [部署教程](Deployment.md) 中所需要的环境依赖

我会尽可能保证这篇教程以及最终运行的代码在 CPU 下也能够推理，但为了获得更好的体验和运行速度，还是非常推荐你拥有一块支持 CUDA 的显卡来运行

## 牛牛唱歌 (Sing)

1. 下载模型相关文件（文件太大了，请加开发 QQ 群：716692626），解压放到 `resource/sing/models/{speaker}` 文件夹里
2. 更新 git 子模块

    ```
    git submodule update --init --recursive
    ```

3. 安装额外依赖，二选一

    - CPU  

        该功能本身约需要 4G 内存，而且比较慢，E3 1230 v2 合成 60 秒音频大概三五分钟（体感，我没具体测）

        ```
        python -m pip install -r src/plugins/sing/requirements.txt
        python -m pip install torch==1.10.0+cpu torchvision==0.11.0+cpu torchaudio==0.10.0 -f https://download.pytorch.org/whl/torch_stable.html
        ```

    - GPU  

        需要 5G 或更高**显存**，否则跑不起来，P106-100 (差不多 GTX1060 的性能）合成 60 秒音频大概需要 30 秒

        ```
        python -m pip install -r src/plugins/sing/requirements.txt
        python -m pip install torch==1.10.0+cu113 torchvision==0.11.0+cu113 torchaudio==0.10.0 -f https://download.pytorch.org/whl/torch_stable.html
        ```

### 牛牛画画

敬请期待

### 牛牛 Chat

1. 下载模型，参考 [原仓库说明](https://github.com/BlinkDL/ChatRWKV#%E4%B8%AD%E6%96%87%E6%A8%A1%E5%9E%8B)，把文件放到 `resource/chat/models` 文件夹，然后改下 `src/chat/answer.py` 里 `args.MODEL_NAME` 的路径
2. 安装依赖

    - CPU

    ```bash
    python -m pip install torch torchvision torchaudio tokenizers
    ```

    - GPU
    
    ```bash
    python -m pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu117
    python -m pip install tokenizers
    ```

3. `src/chat/answer.py` 里的起手咒语 `init_prompt` 有兴趣可以试着改改
