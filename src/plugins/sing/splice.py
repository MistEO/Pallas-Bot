from pydub import AudioSegment
from pathlib import Path
import os


def splice(input_dir: Path, output_dir: Path, total: int, song_id: str, speaker: str, input_format: str = 'mp3', format: str = 'mp3', key: int = 0):
    output_audio = AudioSegment.empty()
    # 拼接音频
    for i in range(total):
        filePath = f'{input_dir}\{song_id}_chunk{i}_{key}key_{speaker}.{input_format}'
        audio = AudioSegment.from_file(filePath)
        output_audio += audio
    print('splicing audio...')

    # 检查输出路径是否存在，如果不存在则创建
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 拼接输出文件的完整路径
    output_file_path = output_dir / f"{song_id}_{speaker}.{format}"
    output_audio.export(output_file_path, format=format)

    return output_file_path
