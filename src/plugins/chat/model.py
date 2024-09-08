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

from rwkv.model import RWKV
from .prompt import INIT_PROMPT, CHAT_FORMAT
from .pipeline import PIPELINE, PIPELINE_ARGS

DEFAULT_STRATEGY = 'cuda fp16' if cuda else 'cpu fp32'
DEFAULT_MODEL_DIR = Path('resource/chat/models')


class Chat:
    def __init__(self, strategy=DEFAULT_STRATEGY, model_dir=DEFAULT_MODEL_DIR) -> None:
        self.STRATEGY = strategy if strategy else DEFAULT_STRATEGY
        self.MODEL_DIR = model_dir
        self.MODEL_EXT = '.pth'
        self.MODEL_PATH = None
        self.TOKEN_PATH = self.MODEL_DIR / '20B_tokenizer.json'
        for f in self.MODEL_DIR.glob('*'):
            if f.suffix != self.MODEL_EXT:
                continue
            self.MODEL_PATH = f.with_suffix('')
            break
        if not self.MODEL_PATH:
            raise Exception(f'Chat model not found in {self.MODEL_DIR}')
        if not self.TOKEN_PATH.exists():
            raise Exception(f'Chat token not found in {self.TOKEN_PATH}')
        model = RWKV(model=str(self.MODEL_PATH), strategy=self.STRATEGY)
        self.pipeline = PIPELINE(model, str(self.TOKEN_PATH))
        self.args = PIPELINE_ARGS(
            temperature=1.0,
            top_p=0.7,
            alpha_frequency=0.25,
            alpha_presence=0.25,
            token_ban=[0],  # ban the generation of some tokens
            token_stop=[],  # stop generation whenever you see any token here
            ends=('\n'),
            ends_if_too_long=("。", "！", "？", "\n"))

        INIT_STATE = deepcopy(self.pipeline.generate(
            INIT_PROMPT, token_count=200, args=self.args)[1])
        self.all_state = defaultdict(lambda: deepcopy(INIT_STATE))
        self.all_occurrence = {}

        self.chat_locker = Lock()

    def chat(self, session: str, text: str, token_count: int = 50) -> str:
        with self.chat_locker:
            state = self.all_state[session]
            ctx = CHAT_FORMAT.format(text)
            occurrence = self.all_occurrence.get(session, {})

            out, state, occurrence = self.pipeline.generate(
                ctx, token_count=token_count, args=self.args, state=state, occurrence=occurrence)

            self.all_state[session] = deepcopy(state)
            self.all_occurrence[session] = occurrence
            return out.strip()

    def del_session(self, session: str):
        with self.chat_locker:
            if session in self.all_state:
                del self.all_state[session]
            if session in self.all_occurrence:
                del self.all_occurrence[session]


if __name__ == "__main__":
    chat = Chat('cpu fp32')
    while True:
        session = "main"
        text = input('text:')
        result = chat.chat(session, text)
        print(result)
