import ast
import os
import json
import requests
import re
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

# ==========================================
# 1. 通用工具函数模块
# ==========================================

def get_template_vars(template_path):
    doc = DocxTemplate(template_path)
    variables = doc.get_undeclared_template_variables()
    return [v for v in variables if not v.startswith(('code_', 'result_image', 'hw_env', 'sw_env'))]

def clean_list_text(raw_data, allow_bullet=False):
    if isinstance(raw_data, list):
        valid_items = [str(item).strip() for item in raw_data if str(item).strip()]
        if allow_bullet:
            return "\n".join([f"{i+1}. {item}" for i, item in enumerate(valid_items)])
        else:
            return " ".join(valid_items)
            
    text = str(raw_data).strip()
    if not allow_bullet:
        text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)
    return text

# ==========================================
# 2. 核心：通用代码抽象提取器 (AST)
# ==========================================

def extract_code_with_ast(py_file_path):
    if not os.path.exists(py_file_path):
        return {"code_import": "未找到代码", "code_load_model": "未找到代码", "code_robot": "未找到代码", "code_main": "未找到代码"}

    with open(py_file_path, 'r', encoding='utf-8') as f:
        source_code = f.read()

    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        print(f"⚠️ AST 解析失败: {e}")
        return {"code_import": "", "code_load_model": "", "code_robot": "", "code_main": "语法错误无法提取"}

    blocks = {"code_import": [], "code_load_model": [], "code_robot": [], "code_main": []}

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            source = ast.get_source_segment(source_code, node)
            if source: blocks["code_import"].append(source)
        elif isinstance(node, ast.Assign):
            source = ast.get_source_segment(source_code, node)
            if source: blocks["code_load_model"].append(source)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            source = ast.get_source_segment(source_code, node)
            if source:
                lines = source.split('\n')
                if len(lines) > 35:
                    source = "\n".join(lines[:35]) + "\n    # ... [为保持报告精简，此处省略后续长代码逻辑] ..."
                blocks["code_robot"].append(source)
        elif isinstance(node, ast.If):
            try:
                if isinstance(node.test, ast.Compare) and \
                   isinstance(node.test.left, ast.Name) and node.test.left.id == '__name__':
                    source = ast.get_source_segment(source_code, node)
                    if source:
                        lines = source.split('\n')
                        if len(lines) > 15:
                            source = "\n".join(lines[:15]) + "\n    # ... [省略后续主循环执行逻辑] ..."
                        blocks["code_main"].append(source)
            except AttributeError:
                pass

    return {
        "code_import": "\n".join(blocks["code_import"])[:600] + ("\n# ...[省略后续库导入]..." if len(blocks["code_import"]) > 10 else ""),
        "code_load_model": "\n".join(blocks["code_load_model"])[:800],
        "code_robot": "\n\n".join(blocks["code_robot"])[:1500] if blocks["code_robot"] else "# 未检测到核心类或函数定义",
        "code_main": "\n".join(blocks["code_main"]) if blocks["code_main"] else "# 未检测到标准主程序入口"
    }

def extract_entities_from_code(code_str):
    imports = re.findall(r'^(?:from|import)\s+([a-zA-Z0-9_.]+)', code_str, re.MULTILINE)
    classes = re.findall(r'^class\s+([a-zA-Z0-9_]+)', code_str, re.MULTILINE)
    functions = re.findall(r'^def\s+([a-zA-Z0-9_]+)', code_str, re.MULTILINE)
    
    entities = []
    if imports: entities.append(f"引用的核心库: {', '.join(list(set(imports))[:5])}")
    if classes: entities.append(f"定义的核心类: {', '.join(classes[:3])}")
    if functions: entities.append(f"定义的核心函数: {', '.join(functions[:5])}")
    
    return " | ".join(entities) if entities else "普通逻辑代码"

# ==========================================
# 3. 三脑协同智能体矩阵 (Macro, Micro, QA)
# ==========================================

def call_ai_macro(user_title, full_code, macro_vars):
    if not macro_vars: return {}
    print(f"🧠 [宏观大脑] 正在分析系统架构与全局逻辑 (共 {len(macro_vars)} 个字段)...")
    
    short_code = "\n".join(full_code.split('\n')[:150])
    json_requirements = []
    for var in macro_vars:
        if "purpose" in var or "process" in var:
            json_requirements.append(f'        "{var}": ["核心要点1", "核心要点2", "核心要点3"]')
        else:
            json_requirements.append(f'        "{var}": "结合代码内容，并引入『Agent智能体(感知-决策-执行)』、『LLM大模型对话流』或『多模态协同』等高级工程概念，撰写一段150字以上、极具学术厚度的系统架构分析。严禁带编号。"')
            
    json_keys_str = ",\n".join(json_requirements)

    prompt = f"""
    你是资深人工智能与机器人专家。当前项目：“{user_title}”
    请阅读全局代码摘要：
    ```python
    {short_code}
    ```
    【最高指令】
    1. 你输出的任何内容，必须是可直接用于正式报告的正文。
    2. 绝对不允许重复或照抄我的提示词，直接输出最终结果！
    
    【强制输出 JSON 结构】
    {{
{json_keys_str}
    }}
    """
    try:
        response = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5:7b", "prompt": prompt, "format": "json", "stream": False})
        return json.loads(response.json().get("response", "{}"))
    except Exception as e:
        print(f"❌ 宏观大脑出错: {e}")
        return {}


def call_ai_qa(user_title, log_text, qa_vars):
    if not qa_vars: return {}
    print(f"🕵️ [QA 智能体] 正在基于真实日志提炼现场联调步骤 (共 {len(qa_vars)} 个字段)...")
    
    if not log_text.strip():
        log_text = "[警告] 现场工程师未提供真实运行日志，请仅根据代码推演3个常规测试步骤。"
        
    json_requirements = []
    for var in qa_vars:
        json_requirements.append(f'        "{var}": ["操作步骤1 (必须带上日志中的具体坐标/水果名等参数)", "操作步骤2...", "操作步骤3..."]')
            
    json_keys_str = ",\n".join(json_requirements)

    prompt = f"""
    你是高级现场联调测试工程师。当前项目：“{user_title}”
    
    【设备真实运行日志】
    ```text
    {log_text[-1000:]}
    ```
    
    【你的任务】
    请严格依据上述真实日志，提炼出 3 到 4 个带有极强现场感的联调测试步骤。
    
    【高压红线】
    1. 步骤中【必须】包含日志里出现的真实数据（如：识别到的水果名称、触发的舵机角度、抓取点位等）。
    2. 严禁使用“测试了相关功能”等假大空的废话。
    3. 绝对不允许重复我的提示词，直接按格式输出结果！
    
    【强制输出 JSON 结构】
    {{
{json_keys_str}
    }}
    """
    try:
        response = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5:7b", "prompt": prompt, "format": "json", "stream": False})
        return json.loads(response.json().get("response", "{}"))
    except Exception as e:
        print(f"❌ QA 智能体出错: {e}")
        return {}


def call_ai_micro(var_name, code_snippet):
    print(f"🔬 [微观探针] 正在精细剖析代码块对应字段: {var_name} ...")
    entities_proof = extract_entities_from_code(code_snippet)
    
    prompt = f"""
    你是一个严谨的代码审查员。
    
    【你的任务】
    请阅读下面这【唯一】的一段局部代码，写一段大约 100 字的连续段落，解释它在干什么。
    
    【铁证强制注入与硬件约束】
    1. Python 物理探针已在这段代码中扫描到以下实体：[{entities_proof}]
    2. 你的描述中【必须】原封不动地包含上述探针提供的类名、函数名或库名！
    3. 【硬件警告】：若出现 Robot、Control 等字眼，该设备统一且只能称为 **“五轴机械臂”** 或 **“机械手”**！
    4. 【负面惩罚】：你的任务是剖析当前这【唯一】的代码块，严禁发散脑补！若当前代码未体现应用主程序入口，严禁提及 QApplication、app.exec_() 等逻辑。
    
    局部代码片段：
    ```python
    {code_snippet[:1000]} 
    ```
    
    【格式要求】
    只输出纯文本段落，严禁输出任何 JSON、Markdown 标记、标题等前缀废话！直接开始正文描述。
    """
    try:
        response = requests.post("http://localhost:11434/api/generate", json={"model": "qwen2.5:7b", "prompt": prompt, "stream": False})
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"❌ 微观探针出错: {e}")
        return ""

# ==========================================
# 4. 确定性主控引擎 (Schema-Driven Workflow)
# ==========================================

def build_report_router(py_file, img_file, log_file, output_path, user_title):
    with open(py_file, 'r', encoding='utf-8') as f:
        full_code_text = f.read()

    log_text = ""
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            log_text = f.read()
    else:
        print(f"⚠️ 未检测到真实日志文件 {log_file}，QA 智能体将降级为常规推演。")

    template_type = "complex" if ("import " in full_code_text and len(full_code_text.split('\n')) > 100) else "simple"
    template_path = f"template_{template_type}.docx"
    print(f"🎯 路由判定：自动匹配【{template_type} 通用模板】")

    template_vars = get_template_vars(template_path)
    code_blocks = extract_code_with_ast(py_file) if template_type == "complex" else {"code_main": full_code_text}

    # ----------------------------------------
    # 物理环境提取层 (完全隔离 AI 幻觉)
    # ----------------------------------------
    import_text = code_blocks.get("code_import", "")
    libs = list(set(re.findall(r'^(?:from|import)\s+([a-zA-Z0-9_]+)', import_text, re.MULTILINE)))
    deterministic_sw_env = "Python 3 / " + " / ".join(libs[:8]) if libs else "Python 3 运行环境"
    deterministic_hw_env = "搭载 GPU 的高性能计算平台" if any(k in import_text for k in ["yolov5", "cv2", "torch"]) else "通用计算机环境"

    # ----------------------------------------
    # 智能体任务分发层 (Map-Reduce-QA)
    # ----------------------------------------
    qa_vars = [v for v in template_vars if "process" in v or "result" in v or "test" in v]
    raw_qa_data = call_ai_qa(user_title, log_text, qa_vars)

    macro_vars = [v for v in template_vars if not v.startswith("step_") and v not in qa_vars]
    raw_macro_data = call_ai_macro(user_title, full_code_text, macro_vars)

    micro_data = {}
    API_CONTRACT = {
        "code_import": "step_import_desc",
        "code_load_model": "step_load_desc",
        "code_robot": "step_orchestration_desc",
        "code_main": "step_main_desc"
    }
    
    for ast_key, expected_var in API_CONTRACT.items():
        if expected_var in template_vars:
            target_code_snippet = code_blocks.get(ast_key, "")
            micro_data[expected_var] = call_ai_micro(expected_var, target_code_snippet)
        else:
            print(f"⚠️ 契约缺失：模板中未找到标准变量 {{{{{expected_var}}}}}，跳过生成。")

    # ----------------------------------------
    # 最终文档渲染层 (Render)
    # ----------------------------------------
    doc = DocxTemplate(template_path)
    context = {}
    
    for key in macro_vars:
        val = raw_macro_data.get(key, "")
        allow_bullet = True if ("purpose" in key or "process" in key) else False
        context[key] = clean_list_text(val, allow_bullet=allow_bullet)
        
    for key, val in micro_data.items():
        clean_val = re.sub(r'^(这段代码.*?：|【.*?】)', '', val).strip()
        context[key] = clean_val
        
    for key in qa_vars:
        val = raw_qa_data.get(key, "")
        context[key] = clean_list_text(val, allow_bullet=True)

    for key, value in code_blocks.items():
        context[key] = value

    context["exp_title"] = user_title
    context["result_image"] = InlineImage(doc, img_file, width=Mm(140)) if os.path.exists(img_file) else "【未提供截图】"
    
    # 强行注入确定性的物理环境数据
    context["hw_env"] = deterministic_hw_env
    context["sw_env"] = deterministic_sw_env

    try:
        doc.render(context)
        doc.save(output_path)
        print(f"✅ 通用智能体(确定性引擎版)生成完毕，已保存至：{output_path}")
    except Exception as e:
        print(f"❌ Word 渲染失败: {e}")

if __name__ == "__main__":
    print("="*40)
    print("   🤖 通用实验报告智能体 Agent V4.0 (三脑协同版) 启动   ")
    print("="*40)
    USER_TITLE = input("请输入实验报告大标题: ").strip() or "基于视觉与语音的机械臂水果分类"
    build_report_router("experiment.py", "result.jpg", "run.log", f"{USER_TITLE}_智能实验报告.docx", USER_TITLE)