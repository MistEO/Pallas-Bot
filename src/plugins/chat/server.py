from flask import Flask, request, jsonify, send_file
from pathlib import Path
from threading import Lock
from copy import deepcopy
from collections import defaultdict
import os
import torch
import io
import Config
import prompt 
import pipeline
import logging

app = Flask(__name__)

config = Config.Setconfig()
logging.basicConfig(level=logging.INFO)

SERVER_HOST = config.SERVER_HOST
SERVER_PORT = config.SERVER_PORT
TTS_SERVER = config.TTS_SERVER
CHAT_SERVER = config.CHAT_SERVER
CHAT_STRATEGY = config.CHAT_STRATEGY

cuda = torch.cuda.is_available()
os.environ['RWKV_JIT_ON'] = '1'
os.environ["RWKV_CUDA_ON"] = '0'

DEFAULT_STRATEGY = 'cuda fp16' if cuda else 'cpu fp32'
API_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_MODEL_DIR = API_DIR / 'resource' / 'chat' / 'models'

print(f"DEFAULT_MODEL_DIR: {DEFAULT_MODEL_DIR}")
print("Files in directory:")
for f in DEFAULT_MODEL_DIR.iterdir():
    print(f)

if CHAT_SERVER:
    from rwkv.model import RWKV 
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
            self.pipeline = pipeline.PIPELINE(model, str(self.TOKEN_PATH))
            self.args = pipeline.PIPELINE_ARGS(
                temperature=1.0,
                top_p=0.7,
                alpha_frequency=0.25,
                alpha_presence=0.25,
                token_ban=[0],  # ban the generation of some tokens
                token_stop=[],  # stop generation whenever you see any token here
                ends=('\n'),
                ends_if_too_long=("。", "！", "？", "\n"))

            INIT_STATE = deepcopy(self.pipeline.generate(
                prompt.INIT_PROMPT, token_count=200, args=self.args)[1])
            self.all_state = defaultdict(lambda: deepcopy(INIT_STATE))
            self.all_occurrence = {}

            self.chat_locker = Lock()

        def chat(self, session: str, text: str, token_count: int = 50) -> str:
            with self.chat_locker:
                state = self.all_state[session]
                ctx = prompt.CHAT_FORMAT.format(text)
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

    if CHAT_STRATEGY == '':
        chat_instance = Chat(DEFAULT_STRATEGY)
        logging.info(f"Using {DEFAULT_STRATEGY} for chat")
    else:
        chat_instance = Chat(CHAT_STRATEGY)
        logging.info(f"Using {CHAT_STRATEGY} for chat")
    

    @app.route('/chat', methods=['POST'])
    def chat():
        '''
        处理chat的路由
        '''
        try:
            data = request.json
            session = data.get('session', 'main')
            text = data.get('text', '')
            token_count = data.get('token_count', 50) 
            response = chat_instance.chat(session, text, token_count)
            return jsonify({'response': response})
        except Exception as e:
            logging.error(f"Error processing chat request: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/del_session', methods=['DELETE'])
    def del_session():
        try:
            data = request.json
            session = data.get('session', 'main')
            chat_instance.del_session(session)
            return jsonify({'status': 'success'})
        except Exception as e:
            logging.error(f"Error deleting session: {e}")
            return jsonify({'error': str(e)}), 500

if TTS_SERVER:
    import text_to_speech 
    @app.route('/tts', methods=['POST'])
    def text_to_speech_api():
        '''
        处理 tts 的路由
        '''
        try:
            data = request.json
            text = data.get('text', '')
            speed = data.get('speed', 1.0)
            pre_silent = data.get('pre_silent', 0.5)
            post_silent = data.get('post_silent', 1.0)

            bs = text_to_speech.text_2_speech(text, speed, pre_silent, post_silent)
            # 检查生成的音频是否为空
            if not bs or len(bs.getvalue()) == 0:
                logging.error("audio is empty")
                return jsonify({'error': 'audio is empty'}), 500
            
            return send_file(io.BytesIO(bs.getvalue()), mimetype='audio/wav', as_attachment=True, download_name='output.wav')

        except Exception as e:
                logging.error(f"Error processing request: {e}")
                return jsonify({'error': str(e)}), 500

@app.route('/chat/ping', methods=['GET'])
def chat_ping():
    return jsonify({"status": "OK"}), 200

@app.route('/tts/ping', methods=['GET'])
def tts_ping():
    return jsonify({"status": "OK"}), 200

if __name__ == "__main__":
    app.run(host=SERVER_HOST, port=SERVER_PORT)