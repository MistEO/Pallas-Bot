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

def splice(input_song: Path, output_dir: Path, finished: bool, song_id: str,chunk_index: int, speaker: str, input_format: str = 'mp3', format: str = 'mp3', key: int = 0):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    last_file_path = f'{output_dir}\{chunk_index - 1}_{song_id}_{key}key_{speaker}.{input_format}'
    now_file_path = f'{output_dir}\{chunk_index}_{song_id}_{key}key_{speaker}.{input_format}'
    print('splicing audio...')

    # 不是第一段且没有能接的文件，过
    if chunk_index > 0 and (not os.path.exists(last_file_path)):
        return

    # 合并
    if chunk_index == 0:
        output_audio = AudioSegment.empty()
    else:
        output_audio = AudioSegment.from_file(last_file_path)
    output_audio += AudioSegment.from_file(input_song)
    output_audio.export(now_file_path)

    # 保存
    if chunk_index > 0:
        os.remove(last_file_path)
    if finished:
        os.rename(now_file_path, f'{output_dir}\{song_id}_{key}key_{speaker}.{input_format}')
        return Path(f'{output_dir}\{song_id}_{key}key_{speaker}.{input_format}')
