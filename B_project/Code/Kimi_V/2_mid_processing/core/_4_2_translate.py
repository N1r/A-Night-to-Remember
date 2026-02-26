"""
翻译模块 - 字幕翻译入口

负责将切割好的文本块并行发送给 LLM 进行翻译，并对齐时间轴。
"""

import pandas as pd
import json
import concurrent.futures
from contextlib import nullcontext

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.translate_lines import translate_lines
from core._4_1_summarize import search_things_to_note_in_prompt
from core._8_1_audio_task import check_len_then_trim
from core._6_gen_sub import align_timestamp
from core.utils import *
from core.utils.models import *

console = Console()

# 分块参数（可在 config.yaml 中通过 translate.chunk_size / translate.max_sentences 覆盖）
_DEFAULT_CHUNK_SIZE = 600
_DEFAULT_MAX_SENTENCES = 10


def split_chunks_by_chars(chunk_size, max_i):
    """将句子列表按字符数和句子数上限分成若干块"""
    with open(_3_2_SPLIT_BY_MEANING, "r", encoding="utf-8") as file:
        sentences = file.read().strip().split('\n')

    chunks = []
    chunk = ''
    sentence_count = 0
    for sentence in sentences:
        if len(chunk) + len(sentence + '\n') > chunk_size or sentence_count == max_i:
            chunks.append(chunk.strip())
            chunk = sentence + '\n'
            sentence_count = 1
        else:
            chunk += sentence + '\n'
            sentence_count += 1
    chunks.append(chunk.strip())
    return chunks


def get_previous_content(chunks, chunk_index):
    """获取前一块的末尾几行作为上下文"""
    return None if chunk_index == 0 else chunks[chunk_index - 1].split('\n')[-3:]


def get_after_content(chunks, chunk_index):
    """获取后一块的开头几行作为上下文"""
    return None if chunk_index == len(chunks) - 1 else chunks[chunk_index + 1].split('\n')[:2]


def translate_chunk(chunk, chunks, theme_prompt, i):
    """翻译单个文本块，返回 (index, 原文, 译文)"""
    things_to_note_prompt = search_things_to_note_in_prompt(chunk)
    previous_content_prompt = get_previous_content(chunks, i)
    after_content_prompt = get_after_content(chunks, i)
    translation, english_result = translate_lines(
        chunk, previous_content_prompt, after_content_prompt,
        things_to_note_prompt, theme_prompt, i
    )
    return i, english_result, translation


@check_file_exists(_4_2_TRANSLATION)
def translate_all():
    """执行字幕翻译"""
    console.print("[bold green]Start Translating All...[/bold green]")

    chunk_size = load_key("translate.chunk_size") if load_key("translate.chunk_size") else _DEFAULT_CHUNK_SIZE
    max_sentences = load_key("translate.max_sentences") if load_key("translate.max_sentences") else _DEFAULT_MAX_SENTENCES
    chunks = split_chunks_by_chars(chunk_size=chunk_size, max_i=max_sentences)

    with open(_4_1_TERMINOLOGY, 'r', encoding='utf-8') as file:
        theme_prompt = json.load(file).get('theme')

    progress_ctx = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    )

    with progress_ctx as progress:
        task = progress.add_task("[cyan]Translating chunks...", total=len(chunks))

        with concurrent.futures.ThreadPoolExecutor(max_workers=load_key("max_workers")) as executor:
            futures = {executor.submit(translate_chunk, chunk, chunks, theme_prompt, i): i
                       for i, chunk in enumerate(chunks)}
            results = [None] * len(chunks)
            for future in concurrent.futures.as_completed(futures):
                idx, english_result, translation = future.result()
                results[idx] = (idx, english_result, translation)
                progress.update(task, advance=1)

    # results[i] 直接对应 chunks[i]，无需相似度匹配
    src_text, trans_text = [], []
    for i, chunk in enumerate(chunks):
        src_text.extend(chunk.split('\n'))
        trans_text.extend(results[i][2].split('\n'))

    df_text = pd.read_excel(_2_CLEANED_CHUNKS)
    df_text['text'] = df_text['text'].str.strip('"').str.strip()
    df_translate = pd.DataFrame({'Source': src_text, 'Translation': trans_text})
    subtitle_output_configs = [('trans_subs_for_audio.srt', ['Translation'])]
    df_time = align_timestamp(df_text, df_translate, subtitle_output_configs, output_dir=None, for_display=False)

    console.print(df_time)

    df_time['Translation'] = df_time.apply(
        lambda x: check_len_then_trim(x['Translation'], x['duration'])
        if x['duration'] > load_key("min_trim_duration") else x['Translation'],
        axis=1
    )

    console.print(df_time)

    df_time.to_excel(_4_2_TRANSLATION, index=False)
    console.print("[bold green]✅ Translation completed and results saved.[/bold green]")


if __name__ == '__main__':
    translate_all()
