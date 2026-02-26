import os
import sys
import subprocess
import time
import cv2
import datetime
import re
from pathlib import Path
from rich import print as rprint

# ===== 确保能导入 shared =====
_PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from shared.aesthetics import aesthetics
    _AESTHETICS_OK = True
except Exception:
    _AESTHETICS_OK = False

# ============= 1. 全局配置区域 =============

OUTPUT_DIR = "output"
OUTPUT_VIDEO = f"{OUTPUT_DIR}/output_sub.mp4"
ASS_SUB = f"{OUTPUT_DIR}/subtitle.ass"

# Logo 路径：优先从 aesthetics 读取
if _AESTHETICS_OK:
    _logo_cfg = aesthetics.get_logo_config()
    _raw_logo_path = _logo_cfg.get("path", "core/logo.png")
    LOGO_ENABLED = _logo_cfg.get("enabled", True)
else:
    _raw_logo_path = "core/logo.png"
    LOGO_ENABLED = True

# 解析绝对路径，使其不受当前工作目录影响
if not os.path.isabs(_raw_logo_path):
    _possible_path = os.path.join(str(_PROJECT_ROOT), "2_mid_processing", _raw_logo_path)
    if os.path.exists(_possible_path):
        LOGO_PATH = _possible_path
    else:
        LOGO_PATH = os.path.join(str(_PROJECT_ROOT), _raw_logo_path)
else:
    LOGO_PATH = _raw_logo_path

# ============= 2. 核心辅助逻辑 =============

def _hex_to_bgr_ass(hex_color: str) -> str:
    """将 '#RRGGBB' 转为 ASS 的 BGR 格式 '00BBGGRR'"""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"00{b}{g}{r}"


def inject_date_to_ass(ass_path, date_str):
    """
    在 ASS 文件中注入一个永久显示的日期样式和行。
    样式参数从 aesthetics 配置读取。
    """
    if not os.path.exists(ass_path):
        return

    # 从 aesthetics 读取日期水印配置
    if _AESTHETICS_OK:
        date_cfg = aesthetics.get_date_config()
        if not date_cfg.get("enabled", True):
            rprint("[dim]⏭️  日期水印已在 aesthetics 配置中禁用[/dim]")
            return
        font = date_cfg.get("fontname", "Arial")
        fontsize = date_cfg.get("fontsize", 45)
        color_hex = date_cfg.get("color", "#FF8500")
        alignment = date_cfg.get("alignment", 7)
        margin = date_cfg.get("margin", 10)
        duration = date_cfg.get("duration", 10)
    else:
        font, fontsize = "Arial", 45
        color_hex = "#FF8500"
        alignment, margin, duration = 7, 10, 10

    color_bgr = _hex_to_bgr_ass(color_hex)

    with open(ass_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 构建日期样式行
    date_style = (f"Style: DateStyle,{font},{fontsize},"
                  f"&H{color_bgr},&H00000000,&H00000000,&H00000000,"
                  f"0,0,0,0,100,100,0,0,1,2,0,{alignment},{margin},{margin},{margin},1\n")
    # 日期显示时长
    dur_h = duration // 3600
    dur_m = (duration % 3600) // 60
    dur_s = duration % 60
    date_line = f"Dialogue: 0,0:00:00.00,{dur_h}:{dur_m:02d}:{dur_s:02d}.00,DateStyle,,0,0,0,,{date_str}\n"

    new_lines = []
    in_styles = False
    style_added = False
    for line in lines:
        new_lines.append(line)
        if "[V4+ Styles]" in line:
            in_styles = True
        elif line.startswith("[") and in_styles:
            in_styles = False

        if in_styles and line.startswith("Format:") and not style_added:
            new_lines.append(date_style)
            style_added = True
        if "[Events]" in line:
            pass

    new_lines.append(date_line)

    with open(ass_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

def merge_subtitles_to_video(video_file=None, ass_file=None, output_path=None):
    # 1. 基础检查
    actual_ass = ass_file if ass_file else ASS_SUB
    actual_out = output_path if output_path else OUTPUT_VIDEO
    actual_out_dir = os.path.dirname(actual_out) or "."

    if not video_file:
        try:
            from core._1_ytdlp import find_video_files
            video_file = find_video_files()
        except:
            # 搜索当前目录下所有支持的视频格式
            from core.utils.config_utils import load_key
            formats = load_key("allowed_video_formats")
            video_file = None
            for ext in formats:
                match = next(Path(".").glob(f"*.{ext}"), None)
                if match:
                    video_file = str(match)
                    break

    if not video_file or not os.path.exists(video_file):
        rprint("[bold red]❌ 未找到输入视频文件。[/bold red]")
        return False

    if not os.path.exists(actual_ass):
        rprint(f"[bold red]❌ 未找到字幕文件: {actual_ass}。[/bold red]")
        return False

    os.makedirs(actual_out_dir, exist_ok=True)
    
    # 获取日期并注入字幕
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    rprint(f"📝 正在将日期 {today_str} 注入字幕文件: {actual_ass}...")
    inject_date_to_ass(actual_ass, today_str)
    
    video_abs = os.path.abspath(video_file)
    ass_abs = os.path.abspath(actual_ass).replace("\\", "/")
    ass_filter_path = ass_abs.replace(":", "\\:").replace("'", "")

    # 2. 视频属性分析与自适应配置
    cap = cv2.VideoCapture(video_file)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    
    is_portrait = h > w
    if is_portrait:
        rprint("[bold cyan]📱 检测到竖屏视频，启动自适应 1080x1920 模式...[/bold cyan]")
        target_w, target_h = 1080, 1920
    else:
        rprint("[bold cyan]🖥️ 检测到横屏视频，启动自适应 1920x1080 模式...[/bold cyan]")
        target_w, target_h = 1920, 1080

    has_logo = LOGO_ENABLED and os.path.exists(LOGO_PATH)
    overlay_pos = "W-w-20:20" # 默认右上
    
    if has_logo:
        l_margin = 20
        if _AESTHETICS_OK:
            _lcfg = aesthetics.get_logo_config()
            scale = _lcfg.get("scale_portrait", 0.18) if is_portrait else _lcfg.get("scale_landscape", 0.12)
            l_pos = _lcfg.get("position", "top-right")
            l_margin = _lcfg.get("margin", 20)
        else:
            scale = 0.18 if is_portrait else 0.12
            l_pos = "top-right"

        logo_w = int(target_w * scale) # 基于目标分辨率缩放 Logo
        
        # 动态计算位置
        if l_pos == "top-right":
            overlay_pos = f"W-w-{l_margin}:{l_margin}"
        elif l_pos == "top-left":
            overlay_pos = f"{l_margin}:{l_margin}"
        elif l_pos == "bottom-right":
            overlay_pos = f"W-w-{l_margin}:H-h-{l_margin}"
        elif l_pos == "bottom-left":
            overlay_pos = f"{l_margin}:H-h-{l_margin}"

    # 3. FFmpeg 命令构建与编码器自动降级
    from core.utils.config_utils import load_key
    use_gpu = load_key("ffmpeg_gpu")
    
    v_encoder = None
    ffmpeg_cmd = ['ffmpeg', '-y']
    
    # --- 1. 优先尝试 NVIDIA NVENC (H.265/HEVC) ---
    if use_gpu:
        try:
            # 测试 hevc_nvenc 是否可用
            test_nvenc = subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'nullsrc', '-t', '0.1', '-c:v', 'hevc_nvenc', '-f', 'null', '-'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            if test_nvenc.returncode == 0:
                v_encoder = 'hevc_nvenc'
                rprint("[green]🚀 检测到 NVIDIA GPU，已开启 NVENC H.265 硬件加速压制...[/green]")
        except:
            pass

    # --- 2. 尝试 VAAPI (Linux 下支持 AMD/Intel GPU) ---
    if not v_encoder and use_gpu and sys.platform.startswith('linux'):
        va_device = "/dev/dri/renderD128"
        if os.path.exists(va_device):
            try:
                # 优先尝试 hevc_vaapi (H.265)
                test_hevc_vaapi = subprocess.run(['ffmpeg', '-vaapi_device', va_device, '-f', 'lavfi', '-i', 'nullsrc', '-t', '0.1', '-c:v', 'hevc_vaapi', '-f', 'null', '-'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                if test_hevc_vaapi.returncode == 0:
                    v_encoder = 'hevc_vaapi'
                    ffmpeg_cmd.extend(['-vaapi_device', va_device])
                    rprint("[green]🚀 检测到 GPU 硬件，已开启 VAAPI H.265 (HEVC) 硬件加速压制...[/green]")
                else:
                    # 尝试 h264_vaapi (H.264)
                    test_h264_vaapi = subprocess.run(['ffmpeg', '-vaapi_device', va_device, '-f', 'lavfi', '-i', 'nullsrc', '-t', '0.1', '-c:v', 'h264_vaapi', '-f', 'null', '-'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                    if test_h264_vaapi.returncode == 0:
                        v_encoder = 'h264_vaapi'
                        ffmpeg_cmd.extend(['-vaapi_device', va_device])
                        rprint("[green]🚀 检测到 GPU 硬件，已开启 VAAPI H.264 硬件加速压制...[/green]")
            except:
                pass

    # --- 2. 尝试 libsvtav1 (AV1 编码, 高压缩比, 软件编码) ---
    if not v_encoder:
        try:
            test_av1 = subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'nullsrc', '-t', '0.1', '-c:v', 'libsvtav1', '-f', 'null', '-'], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            if test_av1.returncode == 0:
                v_encoder = 'libsvtav1'
                rprint("[green]🚀 使用 libsvtav1 进行高效软件压制...[/green]")
        except:
            pass

    # --- 3. 兜底使用 libx264 ---
    if not v_encoder:
        v_encoder = 'libx264'
        rprint("[blue]ℹ️  硬件加速不可用，回退至 libx264 (CPU) 模式...[/blue]")

    # === 解析原创性配置 ===
    saturation = 1.0
    contrast = 1.0
    dynamic_bg_blur = False

    if _AESTHETICS_OK:
        orig_cfg = aesthetics.get("originality", {})
        saturation = float(orig_cfg.get("saturation", 1.0))
        contrast = float(orig_cfg.get("contrast", 1.0))
        dynamic_bg_blur = bool(orig_cfg.get("dynamic_bg_blur", False))

    # 4. 构建画面滤镜链 (去重黑科技 + 自适应黑边/动态模糊)
    
    # 画质微调基础滤镜
    eq_filter = f"eq=contrast={contrast}:saturation={saturation}"

    if dynamic_bg_blur:
        # 动态高斯模糊填补背景
        base_process = f"{eq_filter},split=2[bg_src][fg_src];[bg_src]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},boxblur=luma_radius=30:luma_power=5[bg];[fg_src]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"
    else:
        # 传统黑边
        base_process = f"{eq_filter},scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"

    # 构建主流程
    if has_logo:
        filter_complex = f"[0:v]{base_process}[base];[base]subtitles='{ass_filter_path}'[v_sub];[1:v]scale={logo_w}:-1[logo];[v_sub][logo]overlay={overlay_pos}[v_out]"
    else:
        filter_complex = f"[0:v]{base_process}[base];[base]subtitles='{ass_filter_path}'[v_out]"

    v_map_target = "v_out"

    # 硬件编码器特有后缀格式要求
    if v_encoder in ['h264_vaapi', 'hevc_vaapi']:
        filter_complex += f";[{v_map_target}]format=nv12,hwupload[v_hw]"
        v_map_target = "v_hw"

    ffmpeg_cmd.extend(['-i', video_abs])
    
    if has_logo:
        ffmpeg_cmd.extend(['-i', os.path.abspath(LOGO_PATH)])
    
    ffmpeg_cmd.extend([
        '-filter_complex', filter_complex,
        '-map', f'[{v_map_target}]',
        '-c:v', v_encoder
    ])

    # 编码参数从 aesthetics 读取
    if _AESTHETICS_OK:
        _enc = aesthetics.get_encoding_config()
        _crf = str(_enc.get("crf", 26))
        _preset = _enc.get("preset", "fast")
    else:
        _crf, _preset = "26", "fast"

    if v_encoder == 'libx264':
        ffmpeg_cmd.extend(['-preset', _preset, '-tune', 'fastdecode', '-crf', _crf])
    elif v_encoder == 'hevc_nvenc':
        # NVENC 参数: -cq 代替 -crf, -preset p1-p7 (p7 最慢质量最好)
        # 映射 fast -> p4, medium -> p5, slow -> p6
        nv_preset = 'p4'
        if _preset == 'medium': nv_preset = 'p5'
        if _preset == 'slow': nv_preset = 'p6'
        if _preset == 'veryslow': nv_preset = 'p7'
        
        ffmpeg_cmd.extend(['-preset', nv_preset, '-rc', 'vbr', '-cq', _crf, '-qmin', _crf, '-qmax', _crf])
    elif v_encoder == 'libsvtav1':
            # libsvtav1 推荐参数: preset 8-10 较快
            ffmpeg_cmd.extend(['-preset', '10', '-crf', '32', '-svtav1-params', 'tune=0'])
    else:
        # H.264 VAAPI 码率控制
        ffmpeg_cmd.extend(['-qp', _crf])

    ffmpeg_cmd.extend(['-threads', '4'])

    ffmpeg_cmd.extend([
        '-c:a', 'copy',
        '-map', '0:a?'
    ])

    ffmpeg_cmd.extend([
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        actual_out
    ])

    # 4. 执行渲染
    rprint(f"🚀 [兼容模式] 开始压制 (日期已集成至字幕流)...")
    start_time = time.time()
    
    try:
        subprocess.run(ffmpeg_cmd, check=True)
        rprint(f"\n✅ 渲染完成! 耗时: {time.time() - start_time:.2f}s")
        rprint(f"📁 文件位置: [bold green]{actual_out}[/bold green]")
        return True
    except subprocess.CalledProcessError as e:
        rprint(f"\n[bold red]❌ FFmpeg 压制失败: {e}[/bold red]")
        return False

if __name__ == "__main__":
    merge_subtitles_to_video()