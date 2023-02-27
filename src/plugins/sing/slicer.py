from pydub import AudioSegment
from pathlib import Path
import os


def slice(path: Path, output_dir: Path, output_stem: str, format: str = 'mp3', size_ms: int = 40000):
    os.makedirs(output_dir, exist_ok=True)
    audio_segment = AudioSegment.from_file(path, format=format)
    total = int(audio_segment.duration_seconds * 1000 / size_ms)  # 计算音频切片后的个数

    results = [output_dir /
               f"{output_stem}_chunk{i}.{format}" for i in range(total + 1)]
    if all([f.exists() for f in results]):
        return results

    print('splitting audio...')
    for i in range(total):
        audio_segment[i * size_ms:(i + 1) * size_ms].export(results[i], format=format)

    # 缺少结尾的音频片段
    audio_segment[total * size_ms:].export(results[-1], format=format)

    return results
