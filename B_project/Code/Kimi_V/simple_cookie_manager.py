"""
simple_cookie_manager.py
------------------------
独立 Cookie 管理 WebUI（最小依赖版本）

运行方式：
    .venv_webui/bin/python simple_cookie_manager.py
"""

from nicegui import ui, app
import sys
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.domain import domain
from web_ui.tabs.cookies import cookie_tab

# 配置
QR_CODE_PATH = PROJECT_ROOT / "output" / "login_qrcode.png"

# 静态文件服务
app.add_static_files('/output', str(PROJECT_ROOT / 'output'))
app.add_static_files('/storage', str(PROJECT_ROOT / 'storage'))

@ui.page('/')
def main_page():
    # Header
    with ui.header().classes('bg-blue-600 items-center h-16 shadow-lg'):
        with ui.row().classes('items-center gap-3 w-full px-6'):
            ui.icon('cookie', size='28px', color='white').classes('animate-pulse')
            ui.label(f'Kimi_V Cookie Manager - {domain.name}').classes('text-xl font-bold text-white')
            
            ui.space()
            
            with ui.row().classes('gap-2'):
                ui.button(icon='info', on_click=lambda: show_info())\
                    .props('flat round color=white')\
                    .tooltip('帮助信息')

    # Main Content
    with ui.column().classes('w-full h-[calc(100vh-64px)] p-4 overflow-auto'):
        cookie_tab()

def show_info():
    with ui.dialog().props('maximized').classes('bg-gray-100').style('border-radius: 12px') as dialog:
        with ui.card().classes('w-full h-full').style('border-radius: 12px;'):
            with ui.card_section().classes('bg-white rounded-lg'):
                ui.markdown('# 🍪 Cookie 管理器帮助').classes('text-2xl font-bold mb-4')
                ui.markdown('''
                    ## 功能说明
                    
                    1. **扫码登录** - 点击平台卡片的扫码按钮，启动浏览器获取二维码
                    2. **验证Cookie** - 检查Cookie是否仍然有效
                    3. **删除Cookie** - 清除不需要的Cookie文件
                    4. **刷新状态** - 更新所有平台的Cookie状态
                    
                    ## 注意事项
                    
                    - 首次扫码登录会创建浏览器配置文件
                    - Cookie保存在 `storage/cookies/` 目录
                    - 支持平台: 抖音、B站、快手、小红书、视频号
                ''').classes('text-sm')
    dialog.open()

def main():
    # 确保必要目录存在
    QR_CODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    ui.run(
        title='Kimi_V Cookie Manager',
        port=8080,
        reload=False,
        show=False,
        host='0.0.0.0'
    )

if __name__ in {"__main__", "__mp_main__"}:
    main()
