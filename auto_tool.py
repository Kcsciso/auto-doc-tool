import ast
import os
import json
import requests
import re
import copy
import json
from crewai import Agent, Task, Crew, Process
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# 让 CrewAI 连接你的本地大模型 (换成你实际的 ngrok 链接或 localhost)
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1" 
os.environ["OPENAI_API_KEY"] = "ollama" # 必填，但随便填什么都行

class AgentMemoryManager:
    """
    Agentic V5.5: 自反思长期记忆中枢 (Long-term Episodic Memory)
    """
    def __init__(self, memory_file="agent_memory.json"):
        self.memory_file = memory_file
        self.rules = self.load_memory()

    def load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_memory(self):
        # 为了防止记忆库无限膨胀导致幻觉，只保留最新、最核心的 5 条元法则
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.rules[-5:], f, ensure_ascii=False, indent=2)

    def add_rule(self, rule):
        clean_rule = rule.strip()
        if clean_rule and clean_rule not in self.rules and "未能提取" not in clean_rule:
            self.rules.append(clean_rule)
            self.save_memory()
            print(f"💡 [记忆中枢] 顿悟并保存了一条新法则: {clean_rule[:30]}...")

    def get_memory_context(self):
        if not self.rules:
            return ""
        rules_text = "\n".join([f"- {r}" for r in self.rules[-5:]])
        return f"\n【长期记忆库：历史复盘总结的学术元法则】\n请务必吸收以下经验进行写作：\n{rules_text}\n"

# 实例化一个全局记忆中枢
memory_bank = AgentMemoryManager()

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

    # 🌟 优化点三：新增核心骨架提取器 (AST Node Manipulator)
    def build_skeleton(node):
        new_node = copy.deepcopy(node) # 深拷贝，防止污染原语法树
        
        # 如果是函数定义
        if isinstance(new_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            docstring = ast.get_docstring(new_node)
            new_body = []
            if docstring:
                new_body.append(new_node.body[0]) # 保留函数的注释说明
            # 掏空具体逻辑，用折叠占位符替代
            new_body.append(ast.Expr(value=ast.Constant(value="... [具体代码逻辑已折叠] ...")))
            new_node.body = new_body
            
        # 如果是类定义
        elif isinstance(new_node, ast.ClassDef):
            docstring = ast.get_docstring(new_node)
            new_body = []
            if docstring:
                new_body.append(new_node.body[0])
            for child in new_node.body:
                # 递归保留类里面的所有子函数/子类的签名
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    new_body.append(build_skeleton(child))
            if not new_body or (len(new_body) == 1 and docstring):
                new_body.append(ast.Expr(value=ast.Constant(value="... [类属性与方法已折叠] ...")))
            new_node.body = new_body
            
        return new_node

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            source = ast.get_source_segment(source_code, node)
            if source: blocks["code_import"].append(source)
        elif isinstance(node, ast.Assign):
            source = ast.get_source_segment(source_code, node)
            if source: blocks["code_load_model"].append(source)
            
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            # 🌟 接入骨架提取逻辑
            skeleton_node = build_skeleton(node)
            try:
                # 使用 Python 3.9+ 的 ast.unparse 将树还原为优雅的代码字符串
                source = ast.unparse(skeleton_node)
            except AttributeError:
                # 如果用户的 Python 版本低于 3.9，降级回旧版的简单行数截断
                source = ast.get_source_segment(source_code, node)
                lines = source.split('\n')
                if len(lines) > 35:
                    source = "\n".join(lines[:35]) + "\n    # ... [为保持报告精简，此处省略后续长代码逻辑] ..."
            if source:
                blocks["code_robot"].append(source)
                
        elif isinstance(node, ast.If):
            try:
                if isinstance(node.test, ast.Compare) and \
                   isinstance(node.test.left, ast.Name) and node.test.left.id == '__name__':
                    source = ast.get_source_segment(source_code, node)
                    if source:
                        lines = source.split('\n')
                        if len(lines) > 20: # 主程序稍微放宽至 20 行
                            source = "\n".join(lines[:20]) + "\n    # ... [主循环调用逻辑已折叠] ..."
                        blocks["code_main"].append(source)
            except AttributeError:
                pass

    return {
        "code_import": "\n".join(blocks["code_import"])[:600] + ("\n# ...[省略后续库导入]..." if len(blocks["code_import"]) > 10 else ""),
        "code_load_model": "\n".join(blocks["code_load_model"])[:800],
        # 放宽骨架的字符限制，因为浓缩的都是精华
        "code_robot": "\n\n".join(blocks["code_robot"])[:3000] if blocks["code_robot"] else "# 未检测到核心类或函数定义", 
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

# 修改点：新增 blackboard 参数，默认为空字典
import requests
import json

def call_ai_macro(user_title, full_code, macro_vars, blackboard=None):
    if not macro_vars: return {}
    blackboard = blackboard or {}
    print(f"🧠 [宏观大脑] 正在分析系统架构与全局逻辑 (启动双重审查机制)...")
    
    short_code = "\n".join(full_code.split('\n')[:150])
    json_requirements = []
    for var in macro_vars:
        if "purpose" in var or "process" in var:
            json_requirements.append(f'        "{var}": ["核心要点1", "核心要点2", "核心要点3"]')
        else:
            json_requirements.append(f'        "{var}": "结合代码内容，撰写一段约150字的系统架构分析。"')
            
    json_keys_str = ",\n".join(json_requirements)

    blackboard_context = ""
    if blackboard:
        blackboard_context = "【微观探针与QA提取的局部关键事实】\n请务必深度融合以下事实撰写总结：\n"
        for key, value in blackboard.items():
            if value and not str(value).startswith(("未找到", "提示：", "#")):
                blackboard_context += f"- {key}: {value}\n"

    # ==========================================
    # Pass 1: 生成初稿
    # ==========================================
    prompt_draft = f"""
    当前工程项目：“{user_title}”
    代码摘要：
    ```python
    {short_code}
    ```
    {blackboard_context}
    
    输出包含以下键的JSON，填入对应分析：
    {{
{json_keys_str}
    }}
    """
    try:
        response_draft = requests.post("http://127.0.0.1:11434/api/generate", json={"model": "qwen2.5:7b", "prompt": prompt_draft, "format": "json", "stream": False})
        draft_json_str = response_draft.json().get("response", "{}")
        
        # ==========================================
        # Pass 2: Critic 学术重写
        # ==========================================
        print(f"🧐 [学术审查特工] 正在对宏观大脑的输出进行学术级去水与润色...")
        critic_prompt = f"""
        你是一位苛刻的顶级工程论文审稿人。请严格审查并重写以下 JSON 草稿中的各个字段值。
        
        【待润色 JSON 草稿】:
        {draft_json_str}
        
        {memory_bank.get_memory_context()}

        【整容手术要求】:
        1. 封杀一切营销词汇和废话（如：“该系统完美实现了”、“不仅...还...”、“极大地提高了”、“体现了智能化”等）。
        2. 剔除所有 AI 八股文味，强制替换为第三人称客观陈述。
        3. 必须保持原始的 JSON 结构和键名（Key）完全不变，只重写对应的值（Value）。
        4. 严禁任何前言后语，直接输出合法的 JSON 数据。
        """
        response_critic = requests.post("http://127.0.0.1:11434/api/generate", json={"model": "qwen2.5:7b", "prompt": critic_prompt, "format": "json", "stream": False})
        return json.loads(response_critic.json().get("response", "{}"))
        
    except Exception as e:
        print(f"❌ 宏观大脑执行出错: {e}")
        return {}

def call_ai_reflection(macro_data_dict):
    """
    后台自反思机制：从刚才生成的宏观总结中，蒸馏出学术写作的“元法则”
    """
    print(f"🧘 [反思特工] 报告生成完毕，正在进行后台经验蒸馏与反思...")
    
    # 提取刚生成的精华内容作为复盘素材
    report_text = "\n".join([str(v) for v in macro_data_dict.values() if isinstance(v, str)])[:800]
    
    prompt = f"""
    你是一个负责自我进化的 AI 架构师。请阅读以下刚刚生成的优秀工程文档片段：
    ```text
    {report_text}
    ```
    【任务】
    请从上述文本中，提炼出 1 条极具指导意义的【学术写作元法则】（Meta-Rule）。
    例如：“当描述UI界面与硬件的交互时，应使用『接管了硬件映射与前端界面交互逻辑』这种表述。”
    
    【约束】
    1. 必须是高度抽象的规则，可以直接指导以后的写作。
    2. 严禁任何废话、问候语或解释。
    3. 只输出这一条纯文本法则。
    """
    
    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": "qwen2.5:7b", "prompt": prompt, "format": "json", "stream": False}
        )
        # 这里为了防止模型包裹 JSON，可以简单粗暴地提取 content
        rule_raw = response.json().get("response", "").strip()
        
        # 简单清洗掉大模型可能加的标点或前缀
        rule_clean = re.sub(r'^(法则[：:]|元法则[：:]|【.*?】|["\'])', '', rule_raw).strip(' "\'')
        memory_bank.add_rule(rule_clean)
        
    except Exception as e:
        print(f"⚠️ 反思特工执行跳过 (不影响报告生成): {e}")

def call_ai_qa(user_title, log_text, qa_vars):
    if not qa_vars: return {}
    print(f"🕵️ [QA 智能体] 正在基于真实日志提炼现场联调步骤 (共 {len(qa_vars)} 个字段)...")
    
    if not log_text.strip():
        log_text = "现场工程师未提供真实运行日志，请仅根据代码推演3个常规测试步骤。"
        
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
        response = requests.post("http://127.0.0.1:11434/api/generate", json={"model": "qwen2.5:7b", "prompt": prompt, "format": "json", "stream": False})
        return json.loads(response.json().get("response", "{}"))
    except Exception as e:
        print(f"❌ QA 智能体出错: {e}")
        return {}


from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI

def call_ai_micro(placeholder_name: str, code_snippet: str) -> str:
    """
    Agentic V5.0: Actor-Critic 对抗审查版微观探针
    """
    local_llm = ChatOpenAI(
        model="qwen2.5:7b", 
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama"
    )

    # 👨‍💻 Actor: 卑微的代码提取员 (只管找事实，不管文笔)
    coder_agent = Agent(
        role='底层逻辑提取员',
        goal='精准剖析目标源码的底层业务逻辑，找出核心变量名。',
        backstory="你是一个硬核程序员，只关心代码在干什么。你不需要在乎文笔，必须提取出真实的变量名、函数名和核心动作。",
        verbose=True, allow_delegation=False, llm=local_llm     
    )

    # 🧐 Critic: 苛刻的顶会审稿人 (专治大白话和口水话)
    critic_agent = Agent(
        role='学术论文审查与润色专家',
        goal='将口语化、大白话的技术草稿，重写为极致严谨的学术/工程规范用语。',
        backstory="你极度反感“这段代码”、“可以看出”、“主要进行了”这种学生腔。你精通被动语态和客观陈述，必须像 IEEE 论文作者一样遣词造句。",
        verbose=True, allow_delegation=False, llm=local_llm
    )

    # 任务1：提取草稿
    draft_task = Task(
        description=(
            f"阅读以下真实源码，提炼其核心动作和使用的变量名：\n"
            f"```python\n{code_snippet}\n```\n"
            f"直接列出它做了什么，不需要任何铺垫。"
        ),
        expected_output="包含真实变量名和执行步骤的粗糙草稿。",
        agent=coder_agent
    )

    # 任务2：学术整容 (自动接收上一步的草稿)
    rewrite_task = Task(
        description=(
            "审查上一步生成的草稿，对其进行【学术整容手术】。\n"
            "【强制红线】：\n"
            "1. 彻底删除“这段代码主要进行了...”、“用于...”等一切大白话和口语。\n"
            "2. 必须使用客观被动语态或陈述句，严禁主观情绪词。\n"
            "3. 必须保留草稿中提取的【真实变量名和类名】（如 cv2, clip_close_degree 等）。\n"
            "4. 输出一段约150字的纯文本正文，严禁任何前言后语或 Markdown 标记。\n\n"
            "【🌟 高级学术化转换案例 (Few-Shot) 🌟】\n"
            "案例 1:\n"
            "输入草稿: 这段代码导入了 cv2 和 numpy 库，还实例化了 YOLOv5 模型。\n"
            "完美输出: 系统底层通过引入 cv2 与 numpy 模块构建了基础计算管道，并在初态配置阶段完成了 YOLOv5 目标检测模型的例化与权重加载。\n\n"
            "案例 2:\n"
            "输入草稿: 代码里定义了 shap_count_circles 和 shape_count_square，用来数圆形和方形。\n"
            "完美输出: 为实现目标特征的量化统计，控制逻辑中预设了 shap_count_circles 与 shape_count_square 作为特定形态的计数寄存变量，以确保状态流转的精确度。\n\n"
            "案例 3:\n"
            "输入草稿: 实例化了 Blinx_Five_Robot_Arm，然后调用了 show() 显示界面。\n"
            "完美输出: 业务主循环通过构建 Blinx_Five_Robot_Arm 核心控制实体接管了硬件映射，并同步触发了前端人机交互界面的渲染呈现。\n\n"
            "请严格模仿上述案例的句式丰富度与学术行文质感，重写当前的草稿！"
            "严禁在正文中解释你是如何写作的，严禁提及'被动语态'、'主观情绪'等规则说明词汇。"
        ),
        expected_output="一段150字以内、符合顶级学术规范且句式多样的纯文本原理解析。",
        agent=critic_agent
    )

    # 启动对抗流水线
    report_crew = Crew(
        agents=[coder_agent, critic_agent],
        tasks=[draft_task, rewrite_task],
        process=Process.sequential
    )

    result = report_crew.kickoff()
    return getattr(result, 'raw', str(result))
# ==========================================
# 4. 确定性主控引擎 (Schema-Driven Workflow)
# ==========================================

# 1. 增加 template_file=None 参数
def build_report_router(py_file, img_file, log_file, output_path, user_title, template_file=None):
    with open(py_file, 'r', encoding='utf-8') as f:
        full_code_text = f.read()

    log_text = ""
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            log_text = f.read()
    else:
        print(f"⚠️ 未检测到真实日志文件 {log_file}，QA 智能体将降级为常规推演。")

    # ----------------------------------------
    # 2. 修改这里的模板路由逻辑
    # ----------------------------------------
    if template_file and os.path.exists(template_file):
        template_path = template_file
        template_type = "custom"  # 🌟 修复 Bug：为自定义模板显式声明 type，防止未定义报错
        print(f"🎯 路由判定：使用用户上传的【自定义模板】 -> {template_path}")
    else:
        # 如果用户没传模板，降级为原有的自动匹配逻辑
        template_type = "complex" if ("import " in full_code_text and len(full_code_text.split('\n')) > 100) else "simple"
        template_path = f"template_{template_type}.docx"
        print(f"🎯 路由判定：未检测到自定义模板，自动匹配【{template_type} 通用模板】")

    # 核心：动态提取用户模板中的变量
    template_vars = get_template_vars(template_path)
    
    # 🌟 修复 Bug：统一进行 AST 解析！
    # 既然微观探针 Micro 需要依赖 AST 分块，我们就应该无条件使用 extract_code_with_ast
    code_blocks = extract_code_with_ast(py_file)
    # ----------------------------------------
    # 物理环境提取层 (完全隔离 AI 幻觉)
    # ----------------------------------------
    import_text = code_blocks.get("code_import", "")
    libs = list(set(re.findall(r'^(?:from|import)\s+([a-zA-Z0-9_]+)', import_text, re.MULTILINE)))
    deterministic_sw_env = "Python 3 / " + " / ".join(libs[:8]) if libs else "Python 3 运行环境"
    deterministic_hw_env = "搭载 GPU 的高性能计算平台" if any(k in import_text for k in ["yolov5", "cv2", "torch"]) else "通用计算机环境"

    # ----------------------------------------
    # 智能体任务分发层 (基于全局黑板的 Actor 流水线)
    # ----------------------------------------
    
    # 🌟 1. 初始化全局黑板
    global_blackboard = {}

    # 🌟 2. 微观探针 (Micro) 率先出动，提炼底层逻辑并写在黑板上
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
            # Micro 提取结论
            result_text = call_ai_micro(expected_var, target_code_snippet)
            micro_data[expected_var] = result_text
            # 写入黑板
            global_blackboard[expected_var] = result_text 
        else:
            print(f"⚠️ 契约缺失：模板中未找到标准变量 {{{{{expected_var}}}}}，跳过生成。")

    # 🌟 3. QA 智能体出动，提炼现场日志并写在黑板上
    qa_vars = [v for v in template_vars if "process" in v or "result" in v or "test" in v]
    raw_qa_data = call_ai_qa(user_title, log_text, qa_vars)
    global_blackboard.update(raw_qa_data) # 将 QA 结论合并进黑板

    # 🌟 4. 宏观大脑 (Macro) 最后压轴出场！携带全局黑板进行高维总结
    macro_vars = [v for v in template_vars if not v.startswith("step_") and v not in qa_vars]
    # 把 global_blackboard 传给 Macro
    raw_macro_data = call_ai_macro(user_title, full_code_text, macro_vars, global_blackboard)

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
        # 1. 斩断开头：清理大模型可能带有的前缀（如“这段代码是：”）
        clean_val = re.sub(r'^(这段代码.*?：|【.*?】)', '', val).strip()
        
        # 2. 🌟 魔法抹除：斩断结尾的“指令泄露”与“邀功”尾巴
        # 匹配诸如“在无需主观情绪词的前提下，以客观被动语态详细描述了技术流程。”
        clean_val = re.sub(r'[,，。]?\s*(以上各部分.*?)?在无需.*?(主观情绪|被动语态|客观).*?流程。?', '', clean_val).strip()
        
        # 3. 终极兜底防线：如果大模型抽风复读了其他的 Prompt 规则，一并斩杀
        clean_val = re.sub(r'[,，。]?\s*[^，。]*?(严格模仿|严禁|纯文本|字以内)[^。]*?。?', '', clean_val).strip()
        
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
        
        # 🌟 修改点：在这里启动后台自反思机制，传入宏观大脑的原始数据
        if raw_macro_data:
            call_ai_reflection(raw_macro_data)
            
    except Exception as e:
        print(f"❌ Word 渲染失败: {e}")

if __name__ == "__main__":
    print("="*40)
    print("   🤖 通用实验报告智能体 Agent V4.0 (三脑协同版) 启动   ")
    print("="*40)
    USER_TITLE = input("请输入实验报告大标题: ").strip() or "基于视觉与语音的机械臂水果分类"
    build_report_router("experiment.py", "result.jpg", "run.log", f"{USER_TITLE}_智能实验报告.docx", USER_TITLE)