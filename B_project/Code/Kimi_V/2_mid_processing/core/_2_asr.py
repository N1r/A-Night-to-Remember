"""
ASR 模块 - 语音识别入口

支持的 runtime（通过 config.yaml 中 whisper.runtime 配置）:
    local       - 本地 WhisperX 模型
    cloud       - 302 API (WhisperX 云端)
    elevenlabs  - ElevenLabs ASR API
    deepgram    - Deepgram Nova-3 API
"""

from core.utils import *
from core.asr_backend.demucs_vl import demucs_audio
from core.asr_backend.audio_preprocess import (
    process_transcription,
    convert_video_to_audio,
    split_audio,
    save_results,
    normalize_audio_volume,
)
from core._1_ytdlp import find_video_files
from core.utils.models import *


def _get_transcribe_fn(runtime: str):
    """根据 runtime 返回对应的转录函数"""
    if runtime == "local":
        from core.asr_backend.whisperX_local import transcribe_audio as ts
        rprint("[cyan]🎤 Transcribing audio with local model...[/cyan]")
    elif runtime == "cloud":
        from core.asr_backend.whisperX_302 import transcribe_audio_302 as ts
        rprint("[cyan]🎤 Transcribing audio with 302 API...[/cyan]")
    elif runtime == "elevenlabs":
        from core.asr_backend.elevenlabs_asr import transcribe_audio_elevenlabs as ts
        rprint("[cyan]🎤 Transcribing audio with ElevenLabs API...[/cyan]")
    elif runtime == "deepgram":
        from core.asr_backend.deepgram import transcribe_audio_deepgram as ts
        rprint("[bold magenta]🚀 使用 Deepgram Nova-3 API (极速模式)...[/bold magenta]")
    else:
        raise ValueError(f"Unknown ASR runtime: {runtime}")
    return ts


@check_file_exists(_2_CLEANED_CHUNKS)
def transcribe():
    """
    执行语音识别。

    内部逻辑:
        1. 视频转音频
        2. 人声分离（可选，由 demucs 配置项控制）
        3. 按时间段分割音频
        4. 逐段 ASR 转录
        5. 合并结果并保存
    """
    # 1. 视频 → 音频
    video_file = find_video_files()
    convert_video_to_audio(video_file)

    # 2. 人声分离（可选）
    if load_key("demucs"):
        demucs_audio()
        vocal_audio = normalize_audio_volume(_VOCAL_AUDIO_FILE, _VOCAL_AUDIO_FILE, format="mp3")
    else:
        vocal_audio = _RAW_AUDIO_FILE

    # 3. 分割音频片段
    segments = split_audio(_RAW_AUDIO_FILE)

    # 4. 逐段转录
    runtime = load_key("whisper.runtime")
    ts = _get_transcribe_fn(runtime)

    all_results = []
    for start, end in segments:
        result = ts(_RAW_AUDIO_FILE, vocal_audio, start, end)
        all_results.append(result)

    # 5. 合并 & 保存
    combined_result = {"segments": []}
    for result in all_results:
        combined_result["segments"].extend(result["segments"])

    df = process_transcription(combined_result)
    save_results(df)


if __name__ == "__main__":
    transcribe()
