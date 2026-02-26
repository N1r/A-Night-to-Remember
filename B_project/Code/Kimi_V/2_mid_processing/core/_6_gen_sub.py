import pandas as pd
import os
import re
from rich.panel import Panel
from rich.console import Console
import autocorrect_py as autocorrect
import pysubs2
from pysubs2 import SSAFile, SSAStyle, SSAEvent
from core.utils import *
from core.utils.models import *
from core.style_manager import get_style_config

console = Console()

# --- SRT 配置 ---
SUBTITLE_OUTPUT_CONFIGS = [
    ('src.srt', ['Source']),
    ('trans.srt', ['Translation']),
    ('src_trans.srt', ['Source', 'Translation']),
    ('trans_src.srt', ['Translation', 'Source'])
]

AUDIO_SUBTITLE_OUTPUT_CONFIGS = [
    ('src_subs_for_audio.srt', ['Source']),
    ('trans_subs_for_audio.srt', ['Translation'])
]


def convert_to_srt_format(start_time, end_time):
    def seconds_to_hmsm(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        milliseconds = int(seconds * 1000) % 1000
        return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"
    return f"{seconds_to_hmsm(start_time)} --> {seconds_to_hmsm(end_time)}"

def remove_punctuation(text):
    text = re.sub(r'\s+', ' ', str(text))
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()

def get_sentence_timestamps_with_indices(df_words, df_sentences):
    time_stamp_list = []
    word_indices_list = []
    full_words_str = ''
    position_to_word_idx = {}
    
    for idx, word in enumerate(df_words['text']):
        clean_word = remove_punctuation(str(word).lower())
        start_pos = len(full_words_str)
        full_words_str += clean_word
        for pos in range(start_pos, len(full_words_str)):
            position_to_word_idx[pos] = idx
    
    current_pos = 0
    for idx, sentence in df_sentences['Source'].items():
        clean_sentence = remove_punctuation(str(sentence).lower()).replace(" ", "")
        sentence_len = len(clean_sentence)
        match_found = False
        while current_pos <= len(full_words_str) - sentence_len:
            if full_words_str[current_pos:current_pos+sentence_len] == clean_sentence:
                start_w_idx = position_to_word_idx[current_pos]
                end_w_idx = position_to_word_idx[current_pos + sentence_len - 1]
                time_stamp_list.append((float(df_words['start'][start_w_idx]), float(df_words['end'][end_w_idx])))
                word_indices_list.append((start_w_idx, end_w_idx))
                current_pos += sentence_len
                match_found = True
                break
            current_pos += 1
        if not match_found:
            time_stamp_list.append((0.0, 0.0))
            word_indices_list.append((None, None))
    return time_stamp_list, word_indices_list

def generate_ass_karaoke(df_words, df_sentences, time_stamps, word_indices, output_path, video_path=None):
    """利用 pysubs2 渲染具备双语卡拉OK特效的 ASS，支持横竖屏自适应"""
    import cv2
    subs = SSAFile()
    
    # 默认 16:9 横屏
    res_x, res_y = 1920, 1080
    is_portrait = False
    
    if video_path and os.path.exists(video_path):
        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        if h > w: # 竖屏
            is_portrait = True
            res_x, res_y = 1080, 1920
            
    subs.info["PlayResX"] = res_x
    subs.info["PlayResY"] = res_y
    
    # 动态获取样式（style_manager 内部自动从 aesthetics 读取当前 preset）
    style_config = get_style_config()
    
    # 深度拷贝并自适应调整
    import copy
    source_style = style_config["source"].copy()
    trans_style = style_config["trans"].copy()
    
    if is_portrait:
        # 竖屏适配：增大字体和边距比例
        source_style['fontsize'] = int(source_style['fontsize'] * 1.5)
        source_style['marginv'] = int(res_y * 0.25)
        trans_style['fontsize'] = int(trans_style['fontsize'] * 1.5)
        trans_style['marginv'] = int(res_y * 0.15)
    
    subs.styles["Default"] = SSAStyle(**source_style)
    subs.styles["Trans"] = SSAStyle(**trans_style)

    for i, idx_range in enumerate(word_indices):
        if idx_range[0] is None: continue
        
        start_ms = int(time_stamps[i][0] * 1000)
        end_ms = int(time_stamps[i][1] * 1000)
        total_duration_ms = end_ms - start_ms
        
        # --- 1. 英文卡拉OK (原生时间轴 - 强制大写) ---
        k_text_eng, last_ms = "", start_ms
        for w_idx in range(idx_range[0], idx_range[1] + 1):
            w_row = df_words.iloc[w_idx]
            w_start, w_end = int(w_row['start'] * 1000), int(w_row['end'] * 1000)
            gap = (w_start - last_ms) // 10
            if gap > 0: k_text_eng += f"{{\\k{gap}}}"
            dur = max(1, (w_end - w_start) // 10)
            
            # 强制英文文本大写，增加权威感
            upper_text = str(w_row['text']).upper()
            k_text_eng += f"{{\\kf{dur}}}{upper_text} "
            last_ms = w_end

        # --- 2. 中文卡拉OK (线性镜像分配) ---
        # 逻辑：将英文的总时长平摊给翻译后的每一个中文字符
        trans_str = str(df_sentences.iloc[i]['Translation']).strip()
        if trans_str:
            char_count = len(trans_str)
            # 计算每个汉字分配的百分秒
            # 我们直接用总时长除以字符数。10ms 为单位。
            avg_dur_cs = max(1, (total_duration_ms // 10) // char_count)
            # 最后一个字符处理余数以对齐总时长
            rem_dur_cs = (total_duration_ms // 10) - (avg_dur_cs * (char_count - 1))
            
            k_text_trans = ""
            for idx, char in enumerate(trans_str):
                current_dur = avg_dur_cs if idx < char_count - 1 else rem_dur_cs
                k_text_trans += f"{{\\kf{max(1, current_dur)}}}{char}"
        else:
            k_text_trans = ""

        # --- 3. 添加进/出场缓动、字距、发光模糊 (时政新闻风) ---
        # \fad(50,0) = 50ms 极快淡入，带有突发新闻的紧凑硬核感
        # \blur1.5 = 提供发光和深邃的软阴影
        # \fsp2.5 = 给英文增加很大字距 (Tracking)，营造国际电讯社的通讯带高级感
        prefix_eng = "{\\fad(50,0)\\blur1.5\\fsp2.5}"
        prefix_trans = "{\\fad(50,0)\\blur1.5}"

        # 添加到事件流 (将特效前缀拼在文本最前面)
        subs.events.append(SSAEvent(start=start_ms, end=end_ms, text=prefix_eng + k_text_eng.strip(), style="Default"))
        subs.events.append(SSAEvent(start=start_ms, end=end_ms, text=prefix_trans + k_text_trans, style="Trans"))

    subs.save(output_path)

def align_timestamp(df_text, df_translate, subtitle_output_configs: list, output_dir: str, for_display: bool = True):
    df_trans_time = df_translate.copy()
    time_stamp_list, word_indices = get_sentence_timestamps_with_indices(df_text, df_translate)
    
    df_trans_time['duration'] = [max(0.0, e - s) for s, e in time_stamp_list]
    df_trans_time['timestamp'] = [convert_to_srt_format(s, e) for s, e in time_stamp_list]

    if for_display:
        # 在生成 ASS 之前，我们不希望在翻译里乱去标点，但 SRT 需要去
        df_trans_time['Translation_SRT'] = df_trans_time['Translation'].apply(lambda x: re.sub(r'[，。]', ' ', str(x)).strip())
    else:
        df_trans_time['Translation_SRT'] = df_trans_time['Translation']

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        # 生成 SRT 时使用处理过的文本
        for filename, columns in subtitle_output_configs:
            # 简单的列名映射，确保 SRT 用的是带空格去标点的
            actual_cols = [c if c != 'Translation' else 'Translation_SRT' for c in columns]
            
            content = ''.join([f"{i+1}\n{row['timestamp']}\n{row[actual_cols[0]].strip()}\n{row[actual_cols[1]].strip() if len(actual_cols)>1 else ''}\n\n" for i, row in df_trans_time.iterrows()]).strip()
            with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
                f.write(content)
        
        # 生成双语卡拉OK ASS
        ass_path = os.path.join(output_dir, "subtitle.ass")
        # 尝试寻找关联的视频文件以进行自适应
        from core._1_ytdlp import find_video_files
        video_path = find_video_files()
        generate_ass_karaoke(df_text, df_translate, time_stamp_list, word_indices, ass_path, video_path)
    
    return df_trans_time

def clean_translation(x):
    if pd.isna(x): return ''
    cleaned = str(x).strip('。').strip('，')
    return autocorrect.format(cleaned)

def align_timestamp_main():
    df_text = pd.read_excel(_2_CLEANED_CHUNKS)
    df_text['text'] = df_text['text'].fillna('').astype(str).str.strip('"').str.strip()
    
    if os.path.exists(_5_SPLIT_SUB):
        df_translate = pd.read_excel(_5_SPLIT_SUB)
        df_translate['Translation'] = df_translate['Translation'].apply(clean_translation)
        align_timestamp(df_text, df_translate, SUBTITLE_OUTPUT_CONFIGS, _OUTPUT_DIR)
    
    if os.path.exists(_5_REMERGED):
        df_audio = pd.read_excel(_5_REMERGED)
        df_audio['Translation'] = df_audio['Translation'].apply(clean_translation)
        align_timestamp(df_text, df_audio, AUDIO_SUBTITLE_OUTPUT_CONFIGS, _AUDIO_DIR)

if __name__ == '__main__':
    align_timestamp_main()