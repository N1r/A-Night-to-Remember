"""
TTS 主模块 - 语音合成入口

此模块已通过 Facade 模式迁移到新架构。
旧接口保持不变以确保向后兼容。

新架构使用方式:
    >>> from videolingo.application.use_cases.generate_audio import GenerateAudioUseCase
    >>> from videolingo.infrastructure.tts.registry import TTSRegistry
    >>> from videolingo.infrastructure.config import ConfigManager
    >>> 
    >>> config = ConfigManager.initialize()
    >>> tts_service = TTSRegistry.get()
    >>> use_case = GenerateAudioUseCase(tts_service)
    >>> result = use_case.execute(request)
"""

# =============================================================================
# 旧版导入（保持兼容）
# =============================================================================

import os
import re
from pydub import AudioSegment

from core.asr_backend.audio_preprocess import get_audio_duration
from core.tts_backend.gpt_sovits_tts import gpt_sovits_tts_for_videolingo
from core.tts_backend.sf_fishtts import siliconflow_fish_tts_for_videolingo
from core.tts_backend.openai_tts import openai_tts
from core.tts_backend.fish_tts import fish_tts
from core.tts_backend.azure_tts import azure_tts
from core.tts_backend.edge_tts import edge_tts
from core.tts_backend.sf_cosyvoice2 import cosyvoice_tts_for_videolingo
from core.tts_backend.custom_tts import custom_tts
from core.prompts import get_correct_text_prompt
from core.tts_backend._302_f5tts import f5_tts_for_videolingo
from core.utils import *

# =============================================================================
# 新版架构 Facade（新代码使用）
# =============================================================================

def _get_tts_service():
    """
    获取新架构的 TTS 服务（内部使用）
    """
    try:
        from videolingo.infrastructure.config import ConfigManager
        from videolingo.infrastructure.tts.registry import TTSRegistry
        
        # 确保配置已初始化
        if not ConfigManager.is_initialized():
            ConfigManager.initialize()
        
        # 获取服务
        return TTSRegistry.get()
    except Exception as e:
        rprint(f"[yellow]Warning: Failed to load new TTS service: {e}[/yellow]")
        return None


def _synthesize_with_new_architecture(text: str, save_as: str, options: dict = None) -> bool:
    """
    使用新架构进行语音合成（内部方法）
    
    Returns:
        是否成功
    """
    from videolingo.application.interfaces import TTSOptions
    from videolingo.domain.entities import AudioSegment
    
    # 获取 TTS 服务
    tts_service = _get_tts_service()
    if tts_service is None:
        return False
    
    # 准备选项
    tts_options = TTSOptions()
    if options:
        tts_options = TTSOptions(
            voice_id=options.get('voice'),
            speed=options.get('speed', 1.0),
            language=options.get('language', 'zh-CN')
        )
    
    # 合成
    try:
        audio = tts_service.synthesize(text, Path(save_as), tts_options)
        return audio.audio_path is not None
    except Exception as e:
        rprint(f"[yellow]New TTS failed: {e}[/yellow]")
        return False


# =============================================================================
# 旧版接口（保持不变以确保兼容）
# =============================================================================

def clean_text_for_tts(text):
    """Remove problematic characters for TTS"""
    chars_to_remove = ['&', '®', '™', '©']
    for char in chars_to_remove:
        text = text.replace(char, '')
    return text.strip()


def tts_main(text, save_as, number, task_df):
    """
    TTS 主函数 - 旧版接口
    
    此函数通过 Facade 桥接新旧架构。
    旧代码无需修改即可继续工作。
    """
    text = clean_text_for_tts(text)
    
    # Check if text is empty or single character
    cleaned_text = re.sub(r'[^\w\s]', '', text).strip()
    if not cleaned_text or len(cleaned_text) <= 1:
        silence = AudioSegment.silent(duration=100)
        silence.export(save_as, format="wav")
        rprint(f"Created silent audio for empty/single-char text: {save_as}")
        return
    
    # Skip if file exists
    if os.path.exists(save_as):
        return
    
    # 尝试使用新架构
    use_new_architecture = False
    try:
        tts_service = _get_tts_service()
        use_new_architecture = tts_service is not None and tts_service.is_available()
    except Exception as e:
        pass
    
    if use_new_architecture:
        try:
            rprint(f"[green]Using new TTS architecture[/green]")
            
            # 获取配置中的音色
            config = load_key
            tts_method = config("tts_method")
            
            # 构建选项
            options = {}
            if tts_method == "edge_tts":
                options['voice'] = config("edge_tts.voice")
            elif tts_method == "azure_tts":
                options['voice'] = config("azure_tts.voice")
            elif tts_method == "openai_tts":
                options['voice'] = config("openai_tts.voice")
            
            # 使用新架构合成
            if _synthesize_with_new_architecture(text, save_as, options):
                return
            else:
                rprint("[yellow]New TTS returned False, falling back to legacy[/yellow]")
                use_new_architecture = False
                
        except Exception as e:
            rprint(f"[yellow]New TTS architecture failed: {e}, falling back to legacy[/yellow]")
            use_new_architecture = False
    
    # 使用旧架构（兼容模式）
    if not use_new_architecture:
        print(f"Generating <{text}...>")
        TTS_METHOD = load_key("tts_method")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt >= max_retries - 1:
                    print("Asking GPT to correct text...")
                    correct_text = ask_gpt(get_correct_text_prompt(text), resp_type="json", log_title='tts_correct_text')
                    text = correct_text['text']
                
                if TTS_METHOD == 'openai_tts':
                    openai_tts(text, save_as)
                elif TTS_METHOD == 'gpt_sovits':
                    gpt_sovits_tts_for_videolingo(text, save_as, number, task_df)
                elif TTS_METHOD == 'fish_tts':
                    fish_tts(text, save_as)
                elif TTS_METHOD == 'azure_tts':
                    azure_tts(text, save_as)
                elif TTS_METHOD == 'sf_fish_tts':
                    siliconflow_fish_tts_for_videolingo(text, save_as, number, task_df)
                elif TTS_METHOD == 'edge_tts':
                    edge_tts(text, save_as)
                elif TTS_METHOD == 'custom_tts':
                    custom_tts(text, save_as)
                elif TTS_METHOD == 'sf_cosyvoice2':
                    cosyvoice_tts_for_videolingo(text, save_as, number, task_df)
                elif TTS_METHOD == 'f5tts':
                    f5_tts_for_videolingo(text, save_as, number, task_df)
                else:
                    raise ValueError(f"Unknown TTS method: {TTS_METHOD}")
                
                # Check generated audio duration
                duration = get_audio_duration(save_as)
                if duration > 0:
                    break
                else:
                    if os.path.exists(save_as):
                        os.remove(save_as)
                    if attempt == max_retries - 1:
                        print(f"Warning: Generated audio duration is 0 for text: {text}")
                        silence = AudioSegment.silent(duration=100)
                        silence.export(save_as, format="wav")
                        return
                    print(f"Attempt {attempt + 1} failed, retrying...")
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"Failed to generate audio after {max_retries} attempts: {str(e)}")
                print(f"Attempt {attempt + 1} failed, retrying...")


if __name__ == "__main__":
    # 测试
    tts_main("你好，这是一个测试。", "test_output.wav", 0, None)
