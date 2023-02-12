from pydub import AudioSegment
from pathlib import Path
import os


def mix(vocals: Path, no_vocals: Path, origin_vocals: Path, output_dir: Path, output_stem: str, extension: str = "mp3"):
    path = output_dir / f'{output_stem}.{extension}'
    if path.exists():
        return path

    if not vocals.exists() or not no_vocals.exists():
        return None

    # 自动增益
    origin_vocals_audio = AudioSegment.from_file(origin_vocals)
    origin_db = origin_vocals_audio.dBFS
    vocals_audio = AudioSegment.from_file(vocals)
    vocals_db = vocals_audio.dBFS
    vocals_audio = vocals_audio.apply_gain(origin_db - vocals_db)

    # 混合
    no_vocals_audio = AudioSegment.from_file(no_vocals)
    mix_audio = vocals_audio.overlay(no_vocals_audio)

    # 保存
    os.makedirs(output_dir, exist_ok=True)
    mix_audio.export(path, format=extension)

    if not path.exists():
        return None

    return path
