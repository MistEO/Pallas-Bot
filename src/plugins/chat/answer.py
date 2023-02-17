import torch
from .ChatRWKV.src.model_run import RWKV_RNN
from .ChatRWKV.src.utils import TOKENIZER
import os
import copy
import types
import gc
import numpy as np
from pathlib import Path
from threading import Lock

np.set_printoptions(precision=4, suppress=True, linewidth=200)
args = types.SimpleNamespace()

print('\n\nChatRWKV project: https://github.com/BlinkDL/ChatRWKV')

########################################################################################################

args.RUN_DEVICE = "cuda"  # cuda // cpu
# fp16 (good for GPU, does NOT support CPU) // fp32 (good for CPU) // bf16 (worse accuracy, supports CPU)
args.FLOAT_MODE = "fp16"

QA_PROMPT = False  # True: Q & A prompt // False: User & Bot prompt
# 中文问答设置QA_PROMPT=True（只能问答，问答效果更好，但不能闲聊） 中文聊天设置QA_PROMPT=False（可以闲聊，但需要大模型才适合闲聊）

# Download RWKV-4 models from https://huggingface.co/BlinkDL (don't use Instruct-test models unless you use their prompt templates)

MODELS = 'resource/chat/models'
for f in os.listdir(MODELS):
    if not f.endswith('.pth'):
        continue
    args.MODEL_NAME = f'{MODELS}/{f}'
    if 'ctx2048' in f:
        args.ctx_len = 2048
    else:
        args.ctx_len = 1024
    break

CHAT_LEN_SHORT = 40
CHAT_LEN_LONG = 150
FREE_GEN_LEN = 200

GEN_TEMP = 1.0
GEN_TOP_P = 0.85

AVOID_REPEAT = '，。：？！'

########################################################################################################

os.environ["RWKV_RUN_DEVICE"] = args.RUN_DEVICE


print(
    f'\nLoading ChatRWKV - "Chinese" - {args.RUN_DEVICE} - {args.FLOAT_MODE} - QA_PROMPT {QA_PROMPT}')


# please tune these (test True/False for all of them). can significantly improve speed.
# torch._C._jit_set_profiling_executor(True)
# torch._C._jit_set_profiling_mode(True)
# torch._C._jit_override_can_fuse_on_cpu(True)
# torch._C._jit_override_can_fuse_on_gpu(True)
# torch._C._jit_set_texpr_fuser_enabled(False)
# torch._C._jit_set_nvfuser_enabled(False)

torch.backends.cudnn.benchmark = True
torch.backends.cudnn.allow_tf32 = True
torch.backends.cuda.matmul.allow_tf32 = True
tokenizer = TOKENIZER(
    str(Path(__file__).parent / "ChatRWKV" / "20B_tokenizer.json"))

args.vocab_size = 50277
args.head_qk = 0
args.pre_ffn = 0
args.grad_cp = 0
args.my_pos_emb = 0
MODEL_NAME = args.MODEL_NAME


# Load Model

print(f'Loading model - {MODEL_NAME}')
model = RWKV_RNN(args)

model_tokens = []
model_state = None

AVOID_REPEAT_TOKENS = []
for i in AVOID_REPEAT:
    dd = tokenizer.encode(i)
    assert len(dd) == 1
    AVOID_REPEAT_TOKENS += dd

########################################################################################################

user = "博士"
bot = "牛牛"
interface = ": "

init_prompt = f'''
{bot}真名叫帕拉斯，年轻女性，曾经生活在米诺斯，现在在罗德岛工作，{bot}的头上有一朵花、一对角，喜欢喝酒、蹦迪、逛庆典。
{user}是罗德岛的领袖阿米娅的顾问，而罗德岛是一个医疗组织，他们的目标是拯救矿石病感染者
以下是{bot}与{user}的对话：

{user}{interface}你是谁？

{bot}{interface}我是帕拉斯，也可以叫我牛牛

{user}{interface}我是谁？

{bot}{interface}你是博士呀

{user}{interface}你喜欢喝酒吗？

{bot}{interface}喜欢，要不要来一杯？

{user}{interface}你好笨

{bot}{interface}这对角可能会不小心撞倒些家具，我会尽量小心。

'''


def run_rnn(tokens, newline_adj=0):
    global model_tokens, model_state

    tokens = [int(x) for x in tokens]
    model_tokens += tokens
    out, model_state = model.forward(tokens, model_state)

    # print(f'### model ###\n{tokens}\n[{tokenizer.decode(model_tokens)}]')

    out[0] = -999999999  # disable <|endoftext|>
    out[187] += newline_adj  # adjust \n probability
    # if newline_adj > 0:
    #     out[15] += newline_adj / 2 # '.'
    if model_tokens[-1] in AVOID_REPEAT_TOKENS:
        out[model_tokens[-1]] = -999999999
    return out


all_state = {}
INIT_SESSION = 'chat_init'


def save_all_stat(session: str, last_out):
    all_state[session] = {}
    all_state[session]['out'] = last_out
    all_state[session]['rnn'] = copy.deepcopy(model_state)
    all_state[session]['token'] = copy.deepcopy(model_tokens)


def load_all_stat(session: str):
    global model_tokens, model_state

    if session not in all_state:
        out = load_all_stat(INIT_SESSION)
        save_all_stat(session, out)

    model_state = copy.deepcopy(all_state[session]['rnn'])
    model_tokens = copy.deepcopy(all_state[session]['token'])
    return all_state[session]['out']


def del_all_stat(session: str):
    if session in all_state:
        del all_state[session]

########################################################################################################


# Run inference
print(f'\nRun prompt...')

out = run_rnn(tokenizer.encode(init_prompt))
save_all_stat(INIT_SESSION, out)
gc.collect()
torch.cuda.empty_cache()

print(f'### prompt ###\n[{tokenizer.decode(model_tokens)}]\n')

chat_locker = Lock()


def answer(session: str, text: str):
    with chat_locker:
        global model_tokens, model_state

        out = load_all_stat(session)
        new = f"{user}{interface}{text}\n\n{bot}{interface}"
        out = run_rnn(tokenizer.encode(new), newline_adj=-999999999)
        save_all_stat(session, out)

        ans = ''
        begin = len(model_tokens)
        out_last = begin
        for i in range(999):
            if i <= 0:
                newline_adj = -999999999
            elif i <= CHAT_LEN_SHORT:
                newline_adj = (i - CHAT_LEN_SHORT) / 10
            elif i <= CHAT_LEN_LONG:
                newline_adj = 0
            else:
                newline_adj = (i - CHAT_LEN_LONG) * \
                    0.25  # MUST END THE GENERATION
            token = tokenizer.sample_logits(
                out,
                model_tokens,
                args.ctx_len,
                temperature=GEN_TEMP,
                top_p=GEN_TOP_P,
            )
            out = run_rnn([token], newline_adj=newline_adj)
            xxx = tokenizer.decode(model_tokens[out_last:])
            if '\ufffd' not in xxx:  # avoid utf-8 display issues
                ans += xxx
                # print(xxx, end='', flush=True)
                out_last = begin + i + 1

            send_msg = tokenizer.decode(model_tokens[begin:])
            if '\n\n' in send_msg:
                send_msg = send_msg.strip()
                break

            # send_msg = tokenizer.decode(model_tokens[begin:]).strip()
            # if send_msg.endswith(f'{user}{interface}'): # warning: needs to fix state too !!!
            #     send_msg = send_msg[:-len(f'{user}{interface}')].strip()
            #     break
            # if send_msg.endswith(f'{bot}{interface}'):
            #     send_msg = send_msg[:-len(f'{bot}{interface}')].strip()
            #     break

        # print(f'{model_tokens}')
        # print(f'[{tokenizer.decode(model_tokens)}]')

        save_all_stat(session, out)
        return ans.strip()


if __name__ == "__main__":
    while True:
        session = 1
        text = input('text:')
        answer(session, text)
