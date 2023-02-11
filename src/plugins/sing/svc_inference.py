import os
from pathlib import Path

SVC_MODEL = Path('resource/sing/models/G_60000.pth').absolute()
SVC_CONFIG = Path('resource/sing/models/config.json').absolute()
SVC_HUBERT = Path('resource/sing/models/hubert-soft-0d54a1f4.pt').absolute()
SVC_MAIN = (Path(__file__).parent / 'so_vits_svc' /
            'inference_caller.py').absolute()
SVC_SPEAKER = "pallas"
SVC_SLICE_DB = -40
SVC_OUPUT_FORMAT = 'flac'


def inference(song_path: Path, output_dir: Path, key: int = 0):
    # 这个库不知道咋集成，似乎可以转成 ONNX，但是我不会
    # 先用 cmd 凑合跑了
    # TODO: 使用 ONNX Runtime 重新集成
    result = output_dir / \
        f'{song_path.parent.stem}_{key}key_{SVC_SPEAKER}.{SVC_OUPUT_FORMAT}'

    if not os.path.exists(result):
        cmd = f'python {SVC_MAIN} {SVC_MODEL} {SVC_CONFIG} {SVC_HUBERT} {song_path.absolute()} {key} {SVC_SPEAKER} {SVC_SLICE_DB} {output_dir.absolute()} {SVC_OUPUT_FORMAT}'
        print(cmd)
        os.system(cmd)

    if not os.path.exists(result):
        return None

    return result
