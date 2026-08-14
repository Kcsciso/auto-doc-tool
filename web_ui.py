import gradio as gr
import os
import shutil
from auto_tool import build_report_router

# 1. 在参数列表中新增 template_file
def generate_doc(title, code_file, img_file, log_file, template_file):
    """
    网页端处理函数：交给 Agent 自动路由分发
    """
    if code_file is None:
        return None, "❌ 请上传 Python 源代码文件！"
    
    output_filename = f"{title}_智能实验报告.docx"
    output_path = os.path.join(os.getcwd(), output_filename)
    
    # 1. 修复图片提取：如果不传，给个空字符串，避免读取本地测试残留
    img_path = img_file if isinstance(img_file, str) else (img_file.name if img_file else "")
    
    # 2. 修复日志提取：如果不传，也给空字符串，彻底阻断历史默认日志的干扰
    log_path = log_file if isinstance(log_file, str) else (log_file.name if log_file else "")
    # 3. 新增：安全提取用户上传的模板路径
    template_path = template_file if isinstance(template_file, str) else (template_file.name if template_file else None)
    
    try:
        code_path = code_file if isinstance(code_file, str) else code_file.name
        temp_code_path = "experiment.py"
        shutil.copy(code_path, temp_code_path)
        
        # 3. 新增：将 template_path 传给后端路由
        build_report_router(temp_code_path, img_path, log_path, output_path, title, template_path)
        
        return output_path, "✅ 智能体报告生成成功！已根据您的配置完成深度解析。"
    except Exception as e:
        return None, f"❌ 生成失败，错误信息：{str(e)}"

import gradio as gr
import os
import shutil
from auto_tool import build_report_router

# ==========================================
# 搭建 Agent V4.0 现代化网页界面 (宽屏优化版)
# ==========================================

# 1. 深度定制主题颜色
custom_theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="indigo",
).set(
    button_primary_background_fill="*primary_500",
    button_primary_background_fill_hover="*primary_600",
    button_primary_text_color="white",
    block_radius="lg", # 让所有卡片的圆角更大更现代
)

# 2. 【核心修复】：注入 CSS 限制界面的最大宽度，并居中显示
custom_css = """
.gradio-container {
    max-width: 1100px !important; /* 限制界面最大宽度，宽屏下不再无限拉伸 */
    margin: auto !important;      /* 保证界面整体居中 */
}
"""

with gr.Blocks(title="Auto-Doc-Tool | 实验报告智能生成引擎", theme=custom_theme, css=custom_css) as app:
    
    # 现代化 Header Banner
    gr.HTML("""
        <div style="text-align: center; margin-bottom: 30px; margin-top: 20px;">
            <h1 style="color: #2c3e50; font-size: 2.4em; margin-bottom: 8px; font-weight: 700;">
                Auto-Doc-Tool <span style="color: #3b82f6;">Agent V4.0</span>
            </h1>
            <p style="color: #64748b; font-size: 1.1em; margin-top: 0;">
                基于三脑协同矩阵 (Macro/Micro/QA) 的实验报告自动化生成引擎
            </p>
        </div>
    """)
    
    with gr.Row(equal_height=False):
        # ====================
        # 左侧：操作控制台 (修复重叠问题)
        # ====================
        with gr.Column(scale=12):
            gr.Markdown("### 🛠️ 实验配置台")
            
            with gr.Group():
                in_title = gr.Textbox(label="📌 实验大标题 (自动作为文件名)", placeholder="例如：基于视觉与语音的机械臂物体分类", lines=1)
                # 【修改这里】：去掉了 height=120
                in_code = gr.File(label="🐍 Python 源代码 (.py) [核心必填材料]", file_types=[".py"])
            
            with gr.Accordion("📂 补充材料 (提供后将触发更多智能体推演)", open=False):
                with gr.Row():
                    # 【修改这里】：去掉了 height=150
                    in_img = gr.Image(label="🖼️ 运行截图", type="filepath")
                    in_log = gr.File(label="📜 现场运行日志", file_types=[".log", ".txt"])
            
            with gr.Accordion("⚙️ 高级排版与环境配置", open=False):
                # 【修改这里】：去掉了 height=120
                in_template = gr.File(label="📄 自定义 Word 模板 (.docx)", file_types=[".docx"])
            
            gr.Markdown("<br>") 
            btn_generate = gr.Button("🚀 启动智能体矩阵，一键生成报告", variant="primary", size="lg")
            
        # ====================
        # 中间：留白分割线 (视觉缓冲区)
        # ====================
        with gr.Column(scale=1, min_width=20):
            gr.Markdown("") # 仅作为占位，让左右两侧不要贴得太紧

        # ====================
        # 右侧：输出与指南中心
        # ====================
        with gr.Column(scale=10):
            gr.Markdown("### 🎯 生成结果")
            
            # 卡片组2：输出状态与文件
            with gr.Group():
                out_status = gr.Textbox(label="工作流状态监控", placeholder="等待任务启动...", interactive=False, lines=2)
                out_file = gr.File(label="⬇️ 报告输出口 (点击即可下载)")

            gr.Markdown("<br>")
            
            # 指南面板
            with gr.Accordion("📖 《自定义 Word 模板设计指南》", open=False):
                gr.Markdown("### ⬇️ 默认模板下载")
                with gr.Row():
                    dl_complex = gr.File(value="template_complex.docx", label="高级综合版", interactive=False)
                    dl_simple = gr.File(value="template_simple.docx", label="基础极简版", interactive=False)
                
                gr.Markdown("""
                ---
                ### 🛠️ 占位符魔法
                在 Word 中输入双大括号 `{{ 变量名 }}` 即可唤醒指定 AI 模块：
                *   **基础提取**：`{{ exp_title }}`(标题), `{{ result_image }}`(图片)
                *   **代码原文**：`{{ code_import }}`, `{{ code_load_model }}`, `{{ code_main }}`
                *   **微观探针解析**：`{{ step_import_desc }}`, `{{ step_load_desc }}` (逐行解析)
                *   **唤醒 QA 智能体**：变量名包含 `process`, `result`, `test` 
                *   **唤醒 宏观大脑**：其余所有占位符 (如 `purpose`) 
                """)

    btn_generate.click(
        fn=generate_doc,
        inputs=[in_title, in_code, in_img, in_log, in_template], 
        outputs=[out_file, out_status]
    )

if __name__ == "__main__":
    print("🌐 正在启动 Agent Web 服务...")
    app.launch(server_name="127.0.0.1", server_port=7860, share=False)