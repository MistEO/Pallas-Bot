import os
from threading import Lock
from pathlib import Path


def separate(song_path: Path, output_dir: Path, locker: Lock = Lock()):
    MODEL = 'hdemucs_mmi'
    STEM = song_path.stem

    vocals = output_dir / MODEL / STEM / "vocals.wav"
    no_vocals = output_dir / MODEL / STEM / "no_vocals.wav"

    if not os.path.exists(vocals) or not os.path.exists(no_vocals):
        # 这个库没提供 APIs，暂时简单粗暴用命令行了
        cmd = f'python -m demucs --two-stems=vocals -n {MODEL} {str(song_path)} -o {output_dir}'
        with locker:
            print(cmd)
            os.system(cmd)

    if not os.path.exists(vocals) or not os.path.exists(no_vocals):
        return None

    return vocals, no_vocals
