import os
from threading import Lock
from pathlib import Path


def separate(song_path: Path, output_dir: Path, locker: Lock = Lock()):
    MODEL = 'hdemucs_mmi'
    STEM = song_path.stem

    vocals = output_dir / MODEL / STEM / "vocals.mp3"
    no_vocals = output_dir / MODEL / STEM / "no_vocals.mp3"

    if not vocals.exists() or not no_vocals.exists():
        # 这个库没提供 APIs，暂时简单粗暴用命令行了
        cmd = f'python -m demucs --two-stems=vocals --mp3 --mp3-bitrate 128 -n {MODEL} {str(song_path)} -o {output_dir}'
        with locker:
            print(cmd)
            os.system(cmd)

    if not vocals.exists() or not no_vocals.exists():
        return None

    return vocals, no_vocals
