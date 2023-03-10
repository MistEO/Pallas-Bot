
import paddle
import nltk
import io
import soundfile
import numpy as np
from pathlib import Path
from paddlespeech.t2s.exps.syn_utils import get_am_output, get_frontend, get_predictor, get_voc_output
from threading import Lock

AM_INFERENCE_DIR = Path("resource/tts/models/")
VOC_INFERENCE_DIR = Path("resource/tts/models/vocoder")
nltk.data.path.append('resource/tts/models/nltk_data')

device = "gpu" if paddle.device.is_compiled_with_cuda(
) else "cpu"  # paddle.fluid.is_compiled_with_cuda()
paddle.device.set_device(device)

# frontend
frontend = get_frontend(
    lang="mix",
    phones_dict=AM_INFERENCE_DIR / "phone_id_map.txt",
    tones_dict=None
)


# am_predictor
am_predictor = get_predictor(
    model_dir=AM_INFERENCE_DIR,
    model_file="pallas_jp" + ".pdmodel",
    params_file="pallas_jp" + ".pdiparams",
    device=device)

# voc_predictor
voc_predictor = get_predictor(
    model_dir=VOC_INFERENCE_DIR,
    model_file="pwgan_aishell3" + ".pdmodel",
    params_file="pwgan_aishell3" + ".pdiparams",
    device=device)


SAMPLE_RATE = 24000
predictor_lock = Lock()


def text_2_speech(text: str, speed: int = 1.0, pre_silent: float = 0.5, post_silent: float = 1.0) -> io.BytesIO():
    with predictor_lock:
        am_output_data = get_am_output(
            input=text,
            am_predictor=am_predictor,
            am="fastspeech2_mix",
            frontend=frontend,
            lang="mix",
            merge_sentences=True,
            speaker_dict=AM_INFERENCE_DIR / "phone_id_map.txt",
            spk_id=0, )
        raw = get_voc_output(
            voc_predictor=voc_predictor, input=am_output_data)
    wav = change_speed(raw, speed, SAMPLE_RATE)
    wav = add_silent(wav, SAMPLE_RATE, pre_silent, post_silent)
    bs = io.BytesIO()
    soundfile.write(bs, wav, SAMPLE_RATE, format='wav')
    return bs


def add_silent(sample_raw, sample_rate, pre_silent, post_silent):
    """Add silent to the audio.
    Note that this is an in-place transformation.
    :param pre_silent: Duration of silent to add before the audio.
    :type pre_silent: float
    :param post_silent: Duration of silent to add after the audio.
    :type post_silent: float
    """
    if pre_silent > 0:
        pre_silent = np.zeros(
            [int(sample_rate * pre_silent), 1], dtype=np.float32)
        sample_raw = np.concatenate((pre_silent, sample_raw))
    if post_silent > 0:
        post_silent = np.zeros(
            [int(sample_rate * post_silent), 1], dtype=np.float32)
        sample_raw = np.concatenate((sample_raw, post_silent))
    return sample_raw


def change_speed(sample_raw, speed_rate, sample_rate):
    """Change the audio speed by linear interpolation.
    Note that this is an in-place transformation.
    :param speed_rate: Rate of speed change:
                       speed_rate > 1.0, speed up the audio;
                       speed_rate = 1.0, unchanged;
                       speed_rate < 1.0, slow down the audio;
                       speed_rate <= 0.0, not allowed, raise ValueError.
    :type speed_rate: float
    :raises ValueError: If speed_rate <= 0.0.
    """
    if speed_rate == 1.0:
        return sample_raw
    if speed_rate <= 0:
        raise ValueError("speed_rate should be greater than zero.")

    # numpy
    # old_length = self._samples.shape[0]
    # new_length = int(old_length / speed_rate)
    # old_indices = np.arange(old_length)
    # new_indices = np.linspace(start=0, stop=old_length, num=new_length)
    # self._samples = np.interp(new_indices, old_indices, self._samples)

    # sox, slow
    try:
        import soxbindings as sox
    except ImportError:
        try:
            from paddlespeech.s2t.utils import dynamic_pip_install
            package = "sox"
            dynamic_pip_install.install(package)
            package = "soxbindings"
            dynamic_pip_install.install(package)
            import soxbindings as sox
        except Exception:
            raise RuntimeError("Can not install soxbindings on your system.")

    tfm = sox.Transformer()
    tfm.set_globals(multithread=False)
    tfm.tempo(speed_rate)
    sample_speed = tfm.build_array(
        input_array=sample_raw,
        sample_rate_in=sample_rate).squeeze(-1).astype(np.float32).copy()

    return sample_speed


if __name__ == '__main__':
    import soundfile
    import time
    for i in range(5):
        start_time = time.time()
        bs = text_2_speech("我是来自米诺斯的祭司帕拉斯，会在罗德岛休息一段时间。虽然这么说，我渴望以美酒和戏剧被招待，更渴望走向战场。",
                                speed=1.0)
        duration = time.time() - start_time
        print(f'cost {duration} s')
    with open("hello.wav", "wb") as f:
        f.write(bs.getvalue())
