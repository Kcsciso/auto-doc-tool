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
from tree_sitter import Language, Parser
import tree_sitter_python as tspython

# 让 CrewAI 连接你的本地大模型 (换成你实际的 ngrok 链接或 localhost)
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1" 
os.environ["OPENAI_API_KEY"] = "ollama" # 必填，但随便填什么都行

class AgentMemoryManager:
    """
    Agentic V6.0: 具备语义路由与检索能力的长期记忆中枢 (Semantic Memory Routing)
    """
    def __init__(self, memory_file="agent_memory.json"):
        self.memory_file = memory_file
        self.rules = self.load_memory()

    def load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 兼容老版本的纯列表格式，自动平滑升级为结构化存储
                    if isinstance(data, list):
                        return [{"rule": r, "tags": "general"} for r in data]
                    return data
            except Exception:
                return []
        return []

    def save_memory(self):
        # 2026 演进：不再粗暴截断，允许记忆库沉淀高质量元法则（最多保留 30 条核心经验）
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.rules[-30:], f, ensure_ascii=False, indent=2)

    def add_rule(self, rule):
        clean_rule = rule.strip()
        if not clean_rule or "未能提取" in clean_rule:
            return
            
        # 自动为新法则打上语义标签 (Tags)
        tags = []
        if any(k in clean_rule.lower() for k in ["视觉", "ui", "图像", "cv2", "渲染"]):
            tags.append("vision")
        if any(k in clean_rule.lower() for k in ["硬件", "串口", "机械臂", "映射", "驱动"]):
            tags.append("hardware")
        if not tags:
            tags.append("general")

        # 检查是否重复
        existing_rules = [item["rule"] for item in self.rules]
        if clean_rule not in existing_rules:
            self.rules.append({"rule": clean_rule, "tags": ",".join(tags)})
            self.save_memory()
            print(f"💡 [记忆中枢] 顿悟并结构化存储了新法则 (标签: {tags}): {clean_rule[:30]}...")

    def get_memory_context(self, current_code_snippet=""):
        """
        🌟 2026 核心创新：根据当前代码的内容，动态语义路由相关的历史法则，拒绝一锅端
        """
        if not self.rules:
            return ""
            
        # 如果没有提供代码片段，默认返回最近的 3 条
        if not current_code_snippet:
            recent = self.rules[-3:]
            rules_text = "\n".join([f"- {item['rule']}" for item in recent])
            return f"\n【长期记忆库：历史精选元法则】\n{rules_text}\n"

        # 语义匹配打分
        scored_rules = []
        code_lower = current_code_snippet.lower()
        
        for item in self.rules:
            score = 1  # 基础分
            tags = item["tags"].split(",")
            # 如果法则的标签在当前代码中命中文本，大幅加权
            if "vision" in tags and any(k in code_lower for k in ["cv2", "image", "plt", "show", "camera"]):
                score += 5
            if "hardware" in tags and any(k in code_lower for k in ["port", "arm", "robot", "serial", "control"]):
                score += 5
            scored_rules.append((score, item["rule"]))

        # 按匹配得分排序，取最相关的顶部 4 条法则
        scored_rules.sort(key=lambda x: x[0], reverse=True)
        top_rules = [r[1] for r in scored_rules[:4]]
        
        rules_text = "\n".join([f"- {r}" for r in top_rules])
        return f"\n【长期记忆库：基于当前工程语义智能路由的学术元法则】\n请务必吸收以下高相关经验进行写作：\n{rules_text}\n"

# 实例化一个全局记忆中枢
memory_bank = AgentMemoryManager()

# ==========================================
# 2. 核心：通用代码抽象提取器 (Tree-sitter 装甲版)
# ==========================================

def extract_code_with_ast(py_file_path):
    if not os.path.exists(py_file_path):
        return {"code_import": "未找到代码", "code_load_model": "未找到代码", "code_robot": "未找到代码", "code_main": "未找到代码"}

    with open(py_file_path, 'r', encoding='utf-8') as f:
        source_code = f.read()

    # 🌟 2026 前沿黑科技：启动 Tree-sitter 极限容错解析
    PY_LANGUAGE = Language(tspython.language(), "python")
    parser = Parser()
    parser.set_language(PY_LANGUAGE)
    
    # 哪怕代码写得稀烂（少括号、缩进错），它也绝对不会抛出 SyntaxError，只会强行解析！
    tree = parser.parse(bytes(source_code, "utf8"))
    root_node = tree.root_node

    blocks = {"code_import": [], "code_load_model": [], "code_robot": [], "code_main": []}

    # 辅助函数：提取节点名称
    def get_node_name(node):
        for child in node.children:
            if child.type == 'identifier':
                return child.text.decode('utf8')
        return "unknown"

    # 辅助函数：提取函数/类的注释 (Docstring)
    def get_docstring(node):
        for child in node.children:
            if child.type == 'block':
                if len(child.children) > 0 and child.children[0].type == 'expression_statement':
                    string_node = child.children[0].children[0]
                    if string_node.type == 'string':
                        return string_node.text.decode('utf8').strip('\'" \n')
        return ""

    # 🌟 核心：Tree-sitter 节点转 XML 序列化拓扑
    def build_xml_skeleton_ts(node, depth=0):
        indent = "  " * depth
        
        # 1. 遇到类定义，生成 <Class> 标签
        if node.type == 'class_definition':
            name = get_node_name(node)
            xml_str = f"{indent}<Class name=\"{name}\">\n"
            doc = get_docstring(node)
            if doc:
                clean_doc = doc.split('\n')[0].replace('"', "'")
                xml_str += f"{indent}  <Docstring>{clean_doc}</Docstring>\n"
            
            # 递归挖掘类里面的函数 (Tree-sitter 中，内容通常包裹在 block 节点里)
            for child in node.children:
                if child.type == 'block':
                    for subchild in child.children:
                        if subchild.type in ['function_definition', 'class_definition']:
                            xml_str += build_xml_skeleton_ts(subchild, depth + 1)
            xml_str += f"{indent}</Class>\n"
            return xml_str
            
        # 2. 遇到函数定义，瞬间抽空内部逻辑，只保留纯骨架属性
        elif node.type == 'function_definition':
            name = get_node_name(node)
            doc = get_docstring(node)
            doc_attr = f' doc="{doc.split(chr(10))[0].replace(chr(34), chr(39))}"' if doc else ""
            return f"{indent}<Function name=\"{name}\"{doc_attr} status=\"logic_folded\" />\n"
        
        return ""

    # 遍历根节点下的所有顶层代码块
    for node in root_node.children:
        # 如果解析引擎遇到了乱码或语法错误，它会标记为 ERROR，但程序继续运行！
        if node.type == 'ERROR':
            print("⚠️ [Tree-sitter 探针] 发现代码局部语法损坏，已强行跳过损坏片段！")
            continue
            
        if node.type in ['import_statement', 'import_from_statement']:
            blocks["code_import"].append(node.text.decode('utf8'))
            
        elif node.type == 'assignment' or (node.type == 'expression_statement' and node.children[0].type == 'assignment'):
            blocks["code_load_model"].append(node.text.decode('utf8'))
            
        elif node.type in ['class_definition', 'function_definition']:
            xml_source = build_xml_skeleton_ts(node)
            if xml_source:
                blocks["code_robot"].append(xml_source.strip())
                
        elif node.type == 'if_statement':
            text = node.text.decode('utf8')
            if "__name__" in text and "__main__" in text:
                lines = text.split('\n')
                if len(lines) > 20: 
                    text = "\n".join(lines[:20]) + "\n    # ... [主循环调用逻辑已折叠] ..."
                blocks["code_main"].append(text)

    return {
        "code_import": "\n".join(blocks["code_import"])[:600] + ("\n# ...[省略后续库导入]..." if len(blocks["code_import"]) > 10 else ""),
        "code_load_model": "\n".join(blocks["code_load_model"])[:800],
        # 🌟 组装终极拓扑 XML
        "code_robot": "<ProjectTopology>\n" + "\n\n".join(blocks["code_robot"]) + "\n</ProjectTopology>" if blocks["code_robot"] else "<ProjectTopology><Empty/></ProjectTopology>", 
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
    print(f"🧠 [宏观大脑] 正在分析系统拓扑架构 (启动图谱级双重审查)...")
    
    # 提取前 150 行作为基础参照
    short_code = "\n".join(full_code.split('\n')[:150])
    json_requirements = []
    for var in macro_vars:
        if "purpose" in var or "process" in var:
            json_requirements.append(f'        "{var}": ["核心要点1", "核心要点2", "核心要点3"]')
        else:
            json_requirements.append(f'        "{var}": "结合全局拓扑，撰写一段约150字的系统架构分析。"')
            
    json_keys_str = ",\n".join(json_requirements)

    # 🌟 2026 创新点：将扁平黑板升维成 GraphRAG 语义拓扑协议
    graph_context = ""
    if blackboard:
        graph_context = "【系统实体关系图谱 (Entity-Relationship Graph)】\n"
        graph_context += "以下是底层探针提取的组件级运行事实，请你务必建立它们之间的逻辑调用链条：\n"
        
        # 将无序字典转化为带层级依赖的伪图谱文本
        component_id = 1
        for key, value in blackboard.items():
            if value and not str(value).startswith(("未找到", "提示：", "#")):
                # 动态分配组件层级，引导模型建立上下游关系
                layer = "上层逻辑" if "main" in key else "底层依赖" if "import" in key else "核心中台"
                graph_context += f"  ├── [节点 {component_id} | {layer}] <{key}>\n"
                graph_context += f"  │    └── 核心事实: {value}\n"
                component_id += 1
        graph_context += "  └── 🎯 你的任务：将上述离散节点串联为一套完整的系统架构闭环。\n"

    # ==========================================
    # Pass 1: 生成初稿 (基于图谱上下文)
    # ==========================================
    prompt_draft = f"""
    当前工程项目：“{user_title}”
    代码摘要：
    ```python
    {short_code}
    ```
    {graph_context}
    
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
        print(f"🧐 [学术审查特工] 正在对宏观大脑的输出进行学术级去水与图谱润色...")
        critic_prompt = f"""
        你是一位苛刻的顶级工程论文审稿人。请严格审查并重写以下 JSON 草稿中的各个字段值。
        
        【待润色 JSON 草稿】:
        {draft_json_str}
        
        {memory_bank.get_memory_context()}

        【整容手术要求】:
        1. 封杀一切营销词汇和废话（如：“该系统完美实现了”、“不仅...还...”、“极大地提高了”等）。
        2. 剔除所有 AI 八股文味，强制替换为第三人称客观陈述。
        3. 描述必须体现组件之间的“控制流”或“数据流”关系（例如：A模块将数据透传至B模块，最终驱动C组件）。
        4. 必须保持原始的 JSON 结构和键名（Key）完全不变，只重写对应的值（Value）。
        5. 严禁任何前言后语，直接输出合法的 JSON 数据。
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
    # 智能体任务分发层 (基于图谱语义黑板的 Actor 流水线)
    # ----------------------------------------
    
    # 🌟 1. 初始化全局图谱黑板 (Graph Context)
    global_blackboard = {}

    # 🌟 2. 微观探针 (Micro) 率先出动，提炼底层逻辑
    micro_data = {}
    
    # 【2026 演进】：引入拓扑层级标签 (Topology Tags)
    API_CONTRACT = {
        "code_import": ("step_import_desc", "基础依赖与环境层 (Base Environment)"),
        "code_load_model": ("step_load_desc", "静态资源与模型层 (Static Resources)"),
        "code_robot": ("step_orchestration_desc", "核心业务与逻辑控制层 (Core Logic)"),
        "code_main": ("step_main_desc", "系统顶层调度层 (System Entry)")
    }
    
    for ast_key, (expected_var, layer_tag) in API_CONTRACT.items():
        if expected_var in template_vars:
            target_code_snippet = code_blocks.get(ast_key, "")
            # Micro 提取干瘪的底层事实
            result_text = call_ai_micro(expected_var, target_code_snippet)
            
            # 记录到微观数据池 (保持原汁原味，用于 Word 原样渲染)
            micro_data[expected_var] = result_text
            
            # 🌟 核心：往黑板写入数据时，强行注入图谱层级标签！(给宏观大脑提供导航)
            global_blackboard[expected_var] = f"【属于 {layer_tag}】: {result_text}" 
        else:
            print(f"⚠️ 契约缺失：模板中未找到标准变量 {{{{{expected_var}}}}}，跳过生成。")

    # 🌟 3. QA 智能体出动，提炼现场日志
    qa_vars = [v for v in template_vars if "process" in v or "result" in v or "test" in v]
    raw_qa_data = call_ai_qa(user_title, log_text, qa_vars)
    
    # 将 QA 结论进行时态图谱化后，合并进黑板
    for q_key, q_val in raw_qa_data.items():
        q_text = clean_list_text(q_val, allow_bullet=True)
        # 为 QA 数据打上动态执行状态标签
        global_blackboard[q_key] = f"【系统黑盒运行期的真实表现 (Dynamic Execution State)】: {q_text}"

    # 🌟 4. 宏观大脑 (Macro) 压轴出场！读取结构化图谱进行架构推演
    macro_vars = [v for v in template_vars if not v.startswith("step_") and v not in qa_vars]
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