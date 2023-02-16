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
    file_path = f'{output_dir}\{song_id}_{key}key_{speaker}.{input_format}'
    print('splicing audio...')
    if not os.path.isfile(file_path):
        if chunk_index != 0:
            return
        output_audio = AudioSegment.empty()
    else:
        output_audio = AudioSegment.from_file(file_path)
    output_audio += AudioSegment.from_file(input_song)
    output_audio.export(file_path, format=format)
    if finished:
        mark_file_completed(file_path)

# 在文件末尾添加一个特殊的字符串，用于表示文件已完成
def mark_file_completed(file_path):
    with open(file_path, "a") as f:
        f.write("##FILE_COMPLETED##")
    f.close()

# 检查文件末尾是否有特殊的字符串，用于判断文件是否已完成
def is_file_completed(file_path):
    if not os.path.isfile(file_path):
        return False
    with open(file_path, "rb") as f:
        f.seek(-len("##FILE_COMPLETED##"), 2)
        return f.read() == b"##FILE_COMPLETED##"
