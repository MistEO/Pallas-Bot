import os
from threading import Lock
from pathlib import Path

SVC_HUBERT = Path('resource/sing/models/hubert-soft-0d54a1f4.pt').absolute()
SVC_MAIN = (Path(__file__).parent / 'so_vits_svc' /
            'inference_caller.py').absolute()
SVC_SLICE_DB = -40
SVC_OUPUT_FORMAT = 'flac'

speaker_models = {}


def inference(song_path: Path, output_dir: Path, key: int = 0, speaker: str = "pallas", locker: Lock = Lock()):
    # 这个库不知道咋集成，似乎可以转成 ONNX，但是我不会
    # 先用 cmd 凑合跑了
    # TODO: 使用 ONNX Runtime 重新集成

    result = output_dir / \
        f'{song_path.parent.stem}_{key}key_{speaker}.{SVC_OUPUT_FORMAT}'

    if not result.exists():
        global speaker_models

        model = ""
        if speaker not in speaker_models:
            models_dir = Path(f'resource/sing/models/{speaker}/')
            for m in os.listdir(models_dir):
                if m.startswith('G_') and m.endswith('.pth'):
                    speaker_models[speaker] = models_dir / m
                    break

        model = speaker_models[speaker].absolute()
        config = Path(f'resource/sing/models/{speaker}/config.json').absolute()

        if not os.path.exists(model) or not os.path.exists(config) or not os.path.exists(SVC_HUBERT):
            print("!!! Model or config not found !!!")
            return None

        cmd = f'python {SVC_MAIN} {model} {config} {SVC_HUBERT} {song_path.absolute()} {key} {speaker} {SVC_SLICE_DB} {output_dir.absolute()} {SVC_OUPUT_FORMAT}'
        with locker:
            print(cmd)
            os.system(cmd)

    if not result.exists():
        return None

    return result
