import re

def read_srt_file(file_path: str) -> str:
    """读取本地 .srt 文件并返回提取后的纯文本"""
    try:
        # 推荐使用 utf-8-sig 兼容带 BOM 的 UTF-8，同时 fallback 到 gbk
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='gbk') as f:
                content = f.read()
        
        return simple_read_srt(content)
    
    except FileNotFoundError:
        return "错误：文件未找到。"
    except Exception as e:
        return f"读取出错: {e}"

def simple_read_srt(srt_content: str) -> str:
    """从 SRT 字符串中提取纯文本内容"""
    if not srt_content:
        return ""
    
    # 匹配时间轴行 (如 00:00:01,428 --> 00:00:04,400)
    time_pattern = re.compile(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}')
    lines = srt_content.splitlines()
    clean_text = []
    
    for line in lines:
        line = line.strip()
        # 过滤：空行、纯数字序号行、时间轴行
        if not line or line.isdigit() or time_pattern.match(line):
            continue
        clean_text.append(line)
    
    # 使用空格或换行连接提取到的文字
    return "\n".join(clean_text)

# --- 使用示例 ---
text = read_srt_file("/root/VideoLingo/batch/output/Garcia： If this reporting is accurate on Bovino, it is great news. He/trans.srt")
print(text)