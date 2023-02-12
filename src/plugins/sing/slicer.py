from pydub import AudioSegment
from pathlib import Path
import os


def slice(path: Path, output_dir: Path, output_stem: str, format: str = 'mp3', size: int = 40000):
    os.makedirs(output_dir, exist_ok=True)
    audio_segment = AudioSegment.from_file(path, format=format)
    total = int(audio_segment.duration_seconds * 1000 / size)  # 计算音频切片后的个数

    results = [output_dir /
               f"{output_stem}_chunk{i}.{format}" for i in range(total + 1)]
    if all([f.exists() for f in results]):
        return results

    print('splitting audio...')
    for i in range(total):
        # 将音频切片，并以顺序进行命名
        filename = output_dir / f"{output_stem}_chunk{i}.{format}"
        audio_segment[i * size:(i + 1) * size].export(filename, format=format)
        results.append(filename)

    # 缺少结尾的音频片段
    last_filename = output_dir / f"{output_stem}_chunk{total}.{format}"
    audio_segment[total * size:].export(last_filename, format=format)
    results.append(last_filename)

    return results
