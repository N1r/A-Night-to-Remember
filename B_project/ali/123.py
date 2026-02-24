import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
# 导入所需的类，注意添加了 BrowserConfig
from browser_use import Agent, Browser, ChatBrowserUse

# 1. 加载环境变量 (.env 文件)
load_dotenv()

# 2. 定义绝对路径
BASE_DIR = Path('/home/n1r/桌面/ali')
# ✅ 关键修复：确保传给 Agent 的路径是字符串类型
MP4_PATH = str(BASE_DIR / 'output.mp4')
PNG_PATH = str(BASE_DIR / 'unnamed.jpg')
SESSION_DIR = str(BASE_DIR / 'browser_session') # 用于保存登录状态

async def main():
    # 检查本地文件是否存在
    if not os.path.exists(MP4_PATH) or not os.path.exists(PNG_PATH):
        print(f"❌ 错误：文件未找到！\n请检查: \n{MP4_PATH}\n{PNG_PATH}")
        return

    browser = Browser(
        use_cloud=False,  # Use cloud infrastructure for remote browser
        allowed_domains=[],  # Restrict domains (empty = no restrictions)
    )
    # 4. 初始化 LLM
    llm = ChatBrowserUse(model='bu-latest')

    # 5. 编写任务逻辑
    # 在任务描述中也确保路径是字符串
    task_description = (
        f"1. 访问支付宝创作中心：https://c.alipay.com/page/portal/home\n"
        f"2. 如果未登录，请静止不动，等待我手动完成扫码登录。\n"
        f"3. 登录成功后，寻找并进入视频上传/发布页面。\n"
        f"4. 上传视频文件：{MP4_PATH}\n"
        f"5. 设置视频封面图片：{PNG_PATH}\n"
        f"6. 自动填写标题（可以根据视频文件名起个名字），解决过程中遇到的弹窗，最后尝试点击发布。"
    )

    # 6. 初始化 Agent
    agent = Agent(
        task=task_description,
        llm=llm,
        browser=browser, 
        # ✅ 核心修复：这里的列表成员必须是字符串，不能是 Path 对象
        available_file_paths=[MP4_PATH, PNG_PATH],
        use_vision=True,
        use_thinking=True, # 开启思维模式，有助于解决复杂的弹窗逻辑
        flash_mode=True,
        highlight_elements=True,
    )

    print("🚀 Agent 开始运行...")
    try:
        # 设置 max_steps 以防陷入死循环
        history = await agent.run(max_steps=50)

        # 7. 保存执行结果
        result = history.final_result()
        with open(os.path.join(BASE_DIR, 'final_result.txt'), 'w', encoding='utf-8') as f:
            f.write(result if result else "无返回结果")

        # 保存完整执行日志
        history.save_to_file(os.path.join(BASE_DIR, 'agent_history.json'))
        
        print(f"✅ 任务结束。结果已保存至: {BASE_DIR}")
        print(f"📝 最终摘要: {result}")

    except Exception as e:
        print(f"❌ 运行过程中出现错误: {e}")
    finally:
        # 如果你想在结束后手动检查页面，可以注释掉下面这行
        # await browser.close()
        pass

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 用户手动终止")