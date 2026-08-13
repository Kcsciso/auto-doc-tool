import re
import os
from docxtpl import DocxTemplate

def extract_code_blocks(py_file_path):
    code_blocks = {}
    current_block = None
    current_content = []

    # 降级约束：使用宽容模式提取，免疫隐藏字符和不同操作系统的换行符差异
    start_pattern = re.compile(r'#\s*[-]+\s*([a-zA-Z0-9_]+)\s*[-]+')
    end_pattern = re.compile(r'#\s*[-]+\s*end\s*[-]+')

    if not os.path.exists(py_file_path):
        return code_blocks

    with open(py_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            start_match = start_pattern.search(line)
            end_match = end_pattern.search(line)

            if start_match and not end_match:
                current_block = start_match.group(1)
                current_content = []
            elif end_match and current_block:
                code_blocks[current_block] = "".join(current_content).strip()
                current_block = None
            elif current_block is not None:
                current_content.append(line)

    return code_blocks

def generate_word_report(template_path, py_file_path, output_path):
    print("1. 正在扫描并提取代码区块...")
    context = extract_code_blocks(py_file_path)
    
    if not context:
        print("提取失败，解析引擎未捕获到任何内容。")
        return

    print(f"提取成功，捕获变量: {list(context.keys())}")
    print("2. 加载文档模板...")
    
    try:
        doc = DocxTemplate(template_path)
        print("3. 渲染装配中...")
        doc.render(context)
        doc.save(output_path)
        print("✅ 实验报告生成完毕！")
    except Exception as e:
        print(f"渲染过程发生致命异常: {e}")

if __name__ == "__main__":
    # 维持原路径配置不变
    TEMPLATE_FILE = "template.docx"          
    PY_FILE = "experiment.py"                
    OUTPUT_FILE = "生成的水果分类实验文档.docx" 

    generate_word_report(TEMPLATE_FILE, PY_FILE, OUTPUT_FILE)