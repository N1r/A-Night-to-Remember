import os
import io
import json
import hashlib
from rich import print as rprint
from deepgram import DeepgramClient
from core.utils import load_key

OUTPUT_LOG_DIR = "output/log"

def transcribe_audio_deepgram(raw_audio_path: str, vocal_audio_path: str, start: float = None, end: float = None):
    """
    基于 Deepgram Python SDK v5 标准方法的魔改版本
    """
    os.makedirs(OUTPUT_LOG_DIR, exist_ok=True)
    
    # 1. 缓存逻辑
    file_hash = hashlib.md5(vocal_audio_path.encode()).hexdigest()[:8]
    LOG_FILE = f"{OUTPUT_LOG_DIR}/dg_v5_{file_hash}_{start}_{end}.json"
    if os.path.exists(LOG_FILE):
        return json.load(f := open(LOG_FILE, "r", encoding="utf-8"))

    # 2. 初始化 Client (SDK v5 自动读取环境变量 DEEPGRAM_API_KEY，或手动传入)
    api_key = load_key("whisper.deepgram_api_key")
    deepgram = DeepgramClient(api_key = api_key)

    # 3. 音频裁剪处理
    import librosa
    import soundfile as sf
    try:
        y, sr = librosa.load(vocal_audio_path, sr=16000)
        start = start if start is not None else 0
        end = end if end is not None else len(y)/sr
        y_slice = y[int(start * sr) : int(end * sr)]
        
        # 写入 BytesIO 模拟文件读取
        buffer = io.BytesIO()
        sf.write(buffer, y_slice, sr, format='WAV')
        audio_content = buffer.getvalue()
    except Exception as e:
        rprint(f"[red]❌ 音频裁剪失败: {e}[/red]")
        return {"segments": []}

    # 4. 按照官方 v1.media 规范调用
    try:
        rprint(f"[magenta]🧬 Deepgram Nova-3 (v5 SDK) 转录中: {start:.2f}s[/magenta]")
        
        # 对应你给的官方示例写法
        response = deepgram.listen.v1.media.transcribe_file(
            request=audio_content, # 这里直接传 read() 后的字节流
            model="nova-3",
            smart_format=True,
            #language=load_key("whisper.language") or "zh",
            utterances=True,  # 必须开启以获取 segments 结构
            detect_language = True, # 开启自动检
        )

        # 5. 格式转换适配 (将 v5 Response 对象转为 WhisperX 字典)
        whisperx_style = {"segments": []}
        
        # v5 SDK 返回的是对象，通过属性访问
        if hasattr(response.results, 'utterances') and response.results.utterances:
            for utt in response.results.utterances:
                segment = {
                    "start": float(utt.start) + start,
                    "end": float(utt.end) + start,
                    "text": utt.transcript,
                    "words": [
                        {
                            "word": w.word,
                            "start": float(w.start) + start,
                            "end": float(w.end) + start,
                            "score": getattr(w, 'confidence', 0)
                        } for w in getattr(utt, 'words', [])
                    ]
                }
                whisperx_style["segments"].append(segment)
        else:
            # Fallback: alternatives
            alt = response.results.channels[0].alternatives[0]
            if alt.transcript:
                # 尝试从 alternative 中提取词级别信息（如果有的话）
                words = []
                if hasattr(alt, 'words') and alt.words:
                    for w in alt.words:
                        words.append({
                            "word": w.word,
                            "start": float(w.start) + start,
                            "end": float(w.end) + start,
                            "score": getattr(w, 'confidence', 0)
                        })
                
                whisperx_style["segments"].append({
                    "start": start,
                    "end": end,
                    "text": alt.transcript,
                    "words": words
                })

        # 保存结果
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(whisperx_style, f, indent=4, ensure_ascii=False)
            
        return whisperx_style

    except Exception as e:
        rprint(f"[red]❌ Deepgram API (v5) 异常: {e}[/red]")
        return {"segments": []}