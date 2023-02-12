from pydub import AudioSegment
from pathlib import Path
import os


def mix(vocals: Path, no_vocals: Path, output_dir: Path, output_stem: str, extension: str = "mp3"):
    path = output_dir / f'{output_stem}.{extension}'
    if os.path.exists(path):
        return path

    if not os.path.exists(vocals) or not os.path.exists(no_vocals):
        return None

    # 混合
    vocals_audio = AudioSegment.from_file(vocals)
    no_vocals_audio = AudioSegment.from_file(no_vocals)
    mix_audio = vocals_audio.overlay(no_vocals_audio)

    # 保存
    os.makedirs(output_dir, exist_ok=True)
    mix_audio.export(path, format=extension)

    if not os.path.exists(path):
        return None

    return path
