import gradio as gr
import os
import shutil
# 导入我们升级后的三脑协同总控函数
from auto_tool import build_report_router

def generate_doc(title, code_file, img_file, log_file):
    """
    网页端处理函数：交给 Agent 自动路由分发
    """
    if code_file is None:
        return None, "❌ 请上传 Python 源代码文件！"
    
    output_filename = f"{title}_智能实验报告.docx"
    output_path = os.path.join(os.getcwd(), output_filename)
    
    img_path = img_file.name if img_file else "no_image.jpg"
    # 处理日志文件逻辑：如果有上传就拿真实路径，如果没有就给个默认名字让后端触发降级推演
    log_path = log_file.name if log_file else "run.log"
    
    try:
        # 将代码临时保存为 auto_tool.py 需要的 experiment.py
        temp_code_path = "experiment.py"
        shutil.copy(code_file.name, temp_code_path)
        
        # 触发三脑协同路由 Agent 生成报告 (注意这里新增了 log_path 参数)
        build_report_router(temp_code_path, img_path, log_path, output_path, title)
        
        return output_path, "✅ 智能体报告生成成功！已根据代码与日志完成深度解析。"
    except Exception as e:
        return None, f"❌ 生成失败，错误信息：{str(e)}"

# ==========================================
# 搭建 Agent V4.0 现代化网页界面
# ==========================================
with gr.Blocks(title="AI 实验报告智能体", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 🤖 实验报告智能体 Agent V4.0 (三脑协同版)")
    gr.Markdown("系统已内置**AST 确定性引擎**与**三脑协同矩阵 (宏观/微观/QA)**：实现硬核日志推演与专业理论深度的完美结合。")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📝 第一步：填写实验标题")
            in_title = gr.Textbox(label="实验大标题", placeholder="例如：基于视觉与语音的机械臂物体分类", lines=1)
            
            gr.Markdown("### 📁 第二步：上传实验材料")
            in_code = gr.File(label="上传 Python 源代码 (.py) [必填]", file_types=[".py"])
            in_img = gr.Image(label="上传运行结果截图 (可选)", type="filepath")
            in_log = gr.File(label="上传现场运行日志 (.log / .txt) [可选，触发 QA 智能体现场推演]", file_types=[".log", ".txt"])
            
            btn_generate = gr.Button("🚀 启动智能体生成报告", variant="primary")
            
        with gr.Column(scale=1):
            gr.Markdown("### 📥 第三步：获取定制化报告")
            out_file = gr.File(label="点击下载生成的 Word 文档")
            out_status = gr.Textbox(label="智能体状态", interactive=False)

    btn_generate.click(
        fn=generate_doc,
        inputs=[in_title, in_code, in_img, in_log],  # 增加了 in_log 传参
        outputs=[out_file, out_status]
    )

if __name__ == "__main__":
    print("🌐 正在启动 Agent Web 服务...")
    app.launch(server_name="127.0.0.1", server_port=7860, share=False)