from pathlib import Path
from threading import Lock
from copy import deepcopy
from collections import defaultdict
import os
import torch

cuda = torch.cuda.is_available()
os.environ['RWKV_JIT_ON'] = '1'
# 这个要配个 ninja 啥的环境，能大幅提高推理速度，有需要可以自己弄下（仅支持 cuda 显卡）
os.environ["RWKV_CUDA_ON"] = '0'


from rwkv.model import RWKV  # pip install rwkv
from .pipeline import PIPELINE, PIPELINE_ARGS
from .prompt import INIT_PROMPT, CHAT_FORMAT

# 这个可以照着原仓库的说明改一改，能省点显存啥的
STRATEGY = 'cuda fp16' if cuda else 'cpu fp32'

MODEL_DIR = Path('resource/chat/models')
MODEL_EXT = '.pth'
MODEL_PATH = None
for f in MODEL_DIR.glob('*'):
    if f.suffix != MODEL_EXT:
        continue
    MODEL_PATH = f.with_suffix('')
    break

print('Chat model:', MODEL_PATH)

if not MODEL_PATH:
    print(f'!!!!!!Chat model not found, please put it in {MODEL_DIR}!!!!!!')
    print(f'!!!!!!Chat 模型不存在，请放到 {MODEL_DIR} 文件夹下!!!!!!')
    raise Exception('Chat model not found')

TOKEN_PATH = MODEL_DIR / '20B_tokenizer.json'

if not TOKEN_PATH.exists():
    print(
        f'AI Chat updated, please put token file to {TOKEN_PATH}, download: https://github.com/BlinkDL/ChatRWKV/blob/main/20B_tokenizer.json')
    print(
        f'牛牛的 AI Chat 版本更新了，把 token 文件放到 {TOKEN_PATH} 里再启动, 下载地址：https://github.com/BlinkDL/ChatRWKV/blob/main/20B_tokenizer.json')
    raise Exception('Chat token not found')

model = RWKV(model=str(MODEL_PATH), strategy=STRATEGY)
pipeline = PIPELINE(model, str(TOKEN_PATH))
args = PIPELINE_ARGS(
    temperature=1.0,
    top_p=0.7,
    alpha_frequency=0.25,
    alpha_presence=0.25,
    token_ban=[0],  # ban the generation of some tokens
    token_stop=[],  # stop generation whenever you see any token here
    ends=('\n'),
    ends_if_too_long=("。", "！", "？","\n"))


INIT_STATE = deepcopy(pipeline.generate(
    INIT_PROMPT, token_count=200, args=args)[1])
all_state = defaultdict(lambda: deepcopy(INIT_STATE))
all_occurrence = {}

chat_locker = Lock()


def chat(session: str, text: str, token_count: int = 50) -> str:
    with chat_locker:
        state = all_state[session]
        ctx = CHAT_FORMAT.format(text)
        occurrence = all_occurrence.get(session, {})

        out, state, occurrence = pipeline.generate(
            ctx, token_count=token_count, args=args, state=state, occurrence=occurrence)

        all_state[session] = deepcopy(state)
        all_occurrence[session] = occurrence
        return out.strip()


def del_session(session: str):
    with chat_locker:
        if session in all_state:
            del all_state[session]
        if session in all_occurrence:
            del all_occurrence[session]


if __name__ == "__main__":
    while True:
        session = "main"
        text = input('text:')
        result = chat(session, text)
        print(result)
