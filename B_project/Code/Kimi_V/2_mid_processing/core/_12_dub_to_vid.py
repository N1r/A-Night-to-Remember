import platform
import subprocess

import cv2
import numpy as np
from rich.console import Console

from core._1_ytdlp import find_video_files
from core.asr_backend.audio_preprocess import normalize_audio_volume
from core.utils import *
from core.utils.models import *

console = Console()

DUB_VIDEO = "output/output_dub.mp4"
DUB_SUB_FILE = 'output/dub.srt'
DUB_AUDIO = 'output/dub.mp3'

TRANS_FONT_SIZE = 17
TRANS_FONT_NAME = 'Arial'
if platform.system() == 'Linux':
    TRANS_FONT_NAME = 'NotoSansCJK-Regular'
if platform.system() == 'Darwin':
    TRANS_FONT_NAME = 'Arial Unicode MS'

TRANS_FONT_COLOR = '&H00FFFF'
TRANS_OUTLINE_COLOR = '&H000000'
TRANS_OUTLINE_WIDTH = 1 
TRANS_BACK_COLOR = '&H33000000'

def merge_video_audio():
    """Merge video and audio, and reduce video volume"""
    VIDEO_FILE = find_video_files()
    background_file = _BACKGROUND_AUDIO_FILE
    
    if not load_key("burn_subtitles"):
        rprint("[bold yellow]Warning: A 0-second black video will be generated as a placeholder as subtitles are not burned in.[/bold yellow]")

        # Create a black frame
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(DUB_VIDEO, fourcc, 1, (1920, 1080))
        out.write(frame)
        out.release()

        rprint("[bold green]Placeholder video has been generated.[/bold green]")
        return

    # Normalize dub audio
    normalized_dub_audio = 'output/normalized_dub.wav'
    normalize_audio_volume(DUB_AUDIO, normalized_dub_audio)
    
    # Merge video and audio with translated subtitles
    video = cv2.VideoCapture(VIDEO_FILE)
    TARGET_WIDTH = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    TARGET_HEIGHT = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video.release()
    rprint(f"[bold green]Video resolution: {TARGET_WIDTH}x{TARGET_HEIGHT}[/bold green]")
    
    subtitle_filter = (
        f"subtitles={DUB_SUB_FILE}:force_style='FontSize={TRANS_FONT_SIZE},"
        f"FontName={TRANS_FONT_NAME},PrimaryColour={TRANS_FONT_COLOR},"
        f"OutlineColour={TRANS_OUTLINE_COLOR},OutlineWidth={TRANS_OUTLINE_WIDTH},"
        f"BackColour={TRANS_BACK_COLOR},Alignment=2,MarginV=27,BorderStyle=4'"
    )
    
    cmd = [
        'ffmpeg', '-y', '-i', VIDEO_FILE, '-i', background_file, '-i', normalized_dub_audio,
        '-filter_complex',
        f'[0:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,'
        f'pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2,'
        f'{subtitle_filter}[v];'
        f'[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=3[a]'
    ]

    v_encoder = None
    if load_key("ffmpeg_gpu"):
        # 1. 尝试 NVENC (NVIDIA)
        try:
            test_nvenc = subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'nullsrc', '-t', '0.1', '-c:v', 'hevc_nvenc', '-f', 'null', '-'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            if test_nvenc.returncode == 0:
                v_encoder = 'hevc_nvenc'
                rprint("[green]🚀 检测到 NVIDIA GPU，已开启 NVENC H.265 硬件加速...[/green]")
                cmd.extend(['-c:v', 'hevc_nvenc', '-preset', 'p4', '-rc', 'vbr', '-cq', '26'])
        except:
            pass
        
        # 2. 尝试 VAAPI (Linux/AMD/Intel)
        if not v_encoder and platform.system() == 'Linux':
            va_device = "/dev/dri/renderD128"
            if os.path.exists(va_device):
                try:
                    test_vaapi = subprocess.run(['ffmpeg', '-vaapi_device', va_device, '-f', 'lavfi', '-i', 'nullsrc', '-t', '0.1', '-c:v', 'hevc_vaapi', '-f', 'null', '-'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                    if test_vaapi.returncode == 0:
                        v_encoder = 'hevc_vaapi'
                        cmd = ['ffmpeg', '-vaapi_device', va_device] + cmd[1:] # 把 vaapi_device 插到开头
                        rprint("[green]🚀 检测到 GPU 硬件，已开启 VAAPI H.265 硬件加速...[/green]")
                        cmd.extend(['-c:v', 'hevc_vaapi', '-qp', '26'])
                except:
                    pass

    if not v_encoder:
        rprint("[blue]ℹ️  硬件加速不可用，使用 libx264 (CPU) 模式...[/blue]")
        cmd.extend(['-c:v', 'libx264', '-preset', 'fast', '-crf', '26'])

    cmd.extend(['-map', '[v]', '-map', '[a]', '-c:a', 'aac', '-b:a', '96k', DUB_VIDEO])
    
    subprocess.run(cmd)
    rprint(f"[bold green]Video and audio successfully merged into {DUB_VIDEO}[/bold green]")

if __name__ == '__main__':
    merge_video_audio()
