import os
import time
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
import pickle

# ==================== 配置区 ====================
VIDEO_FOLDER = Path("output/moved_files/done/")
CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_PICKLE = "token.pickle" # 存储授权信息，避免重复登录
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# ==================== 授权逻辑 ====================
def get_authenticated_service():
    credentials = None
    # 检查是否已有缓存的 token
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, 'rb') as token:
            credentials = pickle.load(token)

    # 如果没有有效凭据，则让用户登录
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        # 保存凭据
        with open(TOKEN_PICKLE, 'wb') as token:
            pickle.dump(credentials, token)

    return build('youtube', 'v3', credentials=credentials)

# ==================== 上传函数 ====================
def upload_video(youtube, video_path, title, description="Uploaded via API"):
    """
    上传视频并设置基本信息
    """
    body = {
        'snippet': {
            'title': title[:100], # YouTube 标题上限 100 字符
            'description': description,
            'tags': ['News', 'Bilingual'],
            'categoryId': '25' # 25 代表 News & Politics
        },
        'status': {
            'privacyStatus': 'public', # 'public', 'private', or 'unlisted'
            'selfDeclaredMadeForKids': False,
        }
    }

    # 断点续传设置
    media = MediaFileUpload(
        str(video_path),
        mimetype='video/mp4',
        resumable=True
    )

    request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )

    print(f"🚀 正在上传: {video_path.name}")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  📦 已上传 {int(status.progress() * 100)}%")
    
    video_id = response['id']
    print(f"✅ 上传成功! 视频ID: {video_id}")
    return video_id

def set_thumbnail(youtube, video_id, thumbnail_path):
    """
    为指定视频上传封面图
    """
    if not os.path.exists(thumbnail_path):
        print(f"⚠️ 找不到封面图: {thumbnail_path}")
        return

    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path)
    ).execute()
    print(f"✅ 封面设置成功: {os.path.basename(thumbnail_path)}")

# ==================== 主程序 ====================
def main():
    youtube = get_authenticated_service()
    
    # 查找视频文件
    video_files = list(VIDEO_FOLDER.glob("*.mp4"))
    print(f"📊 找到 {len(video_files)} 个视频等待上传")

    for video_path in video_files:
        try:
            # 1. 上传视频
            # 使用文件名作为标题
            title = video_path.stem
            video_id = upload_video(youtube, video_path, title)

            # 2. 查找并上传封面 (匹配同名的 .jpg 或 .png)
            thumbnail_path = None
            for ext in ['.jpg', '.png', '.jpeg']:
                potential_thumb = video_path.with_suffix(ext)
                if potential_thumb.exists():
                    thumbnail_path = str(potential_thumb)
                    break
            
            if thumbnail_path:
                set_thumbnail(youtube, video_id, thumbnail_path)

            print(f"🏁 {video_path.name} 处理完成\n")
            time.sleep(2) # 避免请求过快

        except Exception as e:
            print(f"❌ 上传 {video_path.name} 时出错: {e}")

if __name__ == "__main__":
    main()
