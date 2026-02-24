import asyncio
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from browser_use import Agent, Browser, ChatBrowserUse

# 1. 加载环境变量
load_dotenv()

# 2. 路径配置
BASE_DIR = Path('/home/n1r/桌面/ali')
MP4_PATH = str(BASE_DIR / 'output.mp4')
PNG_PATH = str(BASE_DIR / 'unnamed.jpg')
# Chromium 配置文件存放目录 (用于持久化登录状态)
SESSION_DIR = str(BASE_DIR / 'browser_session')

async def main():
    # 检查本地文件
    if not os.path.exists(MP4_PATH) or not os.path.exists(PNG_PATH):
        print(f"❌ 错误：文件未找到！请检查路径。")
        return

    # 3. 初始化 Browser (最新版 API：直接传参)
    # 默认使用 Chromium，这是 browser-use 兼容性最好的内核
    browser = Browser(
        headless=False,
        user_data_dir=SESSION_DIR, # ✅ 关键：所有的 Cookies 和登录状态都会存在这里
    )

    # 4. 初始化 LLM
    llm = ChatBrowserUse(model='bu-latest')

    # 5. 任务逻辑
    task_description = (
        f"1. 访问支付宝创作中心：https://c.alipay.com/page/portal/home\n"
        f"2. 如果未登录，请静止不动，等待我手动完成扫码登录。\n"
        f"3. 登录成功后，进入视频上传页面并上传：{MP4_PATH}\n"
        f"4. 设置视频封面图片：{PNG_PATH}\n"
        f"5. 填写标题并发布，处理过程中遇到的弹窗报错。"
    )

    # 6. 初始化 Agent
    agent = Agent(
        task=task_description,
        llm=llm,
        browser=browser,
        available_file_paths=[MP4_PATH, PNG_PATH],
        use_vision=True,
        use_thinking=True, # 开启思维模式
    )

    print("🚀 Agent 开始运行 (Chromium 模式)...")

    try:
        # 执行任务
        history = await agent.run(max_steps=50)

        # ==========================================
        # 📊 改进的输出与保存方法
        # ==========================================
        print("\n📝 任务结束，正在生成详细报告...")

        # A. 保存最终摘要文本
        final_result = history.final_result()
        with open(BASE_DIR / 'final_result.txt', 'w', encoding='utf-8') as f:
            f.write(final_result if final_result else "无返回结果")

        # B. 保存为结构化的 Markdown 报告 (最直观)
        report_path = BASE_DIR / 'execution_report.md'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"# 🎬 自动化执行报告\n\n")
            f.write(f"## 📌 概览\n")
            f.write(f"- **状态**: {'✅ 成功' if history.is_successful() else '⚠️ 未完全成功'}\n")
            f.write(f"- **总时长**: {history.total_duration_seconds():.2f} 秒\n")
            f.write(f"- **执行步数**: {history.number_of_steps()}\n\n")

            f.write(f"## 🏁 最终结果\n> {final_result}\n\n")

            f.write(f"## 🧠 Agent 执行细节\n")
            f.write("| 步骤 | 执行动作 | AI 的思考逻辑 |\n")
            f.write("| :--- | :--- | :--- |\n")

            actions = history.action_names()
            thoughts = history.model_thoughts()

            for i in range(len(actions)):
                # 提取思考内容（如果有的话）
                thought_text = "无"
                if i < len(thoughts):
                    # 获取 reasoning 属性，如果没有则转字符串
                    thought_text = getattr(thoughts[i], 'reasoning', str(thoughts[i]))
                    # 简单清洗一下换行符，防止破坏 Markdown 表格结构
                    thought_text = thought_text.replace('\n', ' ').replace('|', '｜')

                f.write(f"| {i+1} | `{actions[i]}` | {thought_text} |\n")

            # C. 记录错误 (如果有)
            if history.has_errors():
                f.write(f"\n## ❌ 错误摘要\n")
                for i, err in enumerate(history.errors()):
                    if err:
                        f.write(f"- 步骤 {i+1}: {err}\n")

        # D. 保存原始 JSON 历史 (供程序读取)
        history.save_to_file(str(BASE_DIR / 'agent_history.json'))

        print(f"✅ 执行报告已更新至: {report_path}")

    except Exception as e:
        print(f"❌ 运行过程中出现崩溃: {e}")
    finally:
        # 为了调试，暂时不自动关闭浏览器
        # await browser.close()
        pass

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 用户手动终止")
