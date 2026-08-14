# 🤖 Auto-Doc-Tool Agent V4.0
> **基于三脑协同矩阵 (Macro/Micro/QA) 的通用实验报告智能体自动化生成系统**

Auto-Doc-Tool 是一个零人工干预的智能文档生成引擎。只需上传 Python 实验代码、运行截图与现场日志，系统即可通过本地化部署的大语言模型（Ollama + Qwen2.5:7b），自动提取代码 AST 抽象语法树，并结合自定义 Word 模板，一键生成具有极高学术/工程规范感的 `.docx` 实验报告。

---

## ✨ 核心特性 (Core Features)

*   🧠 **三脑协同智能体架构**：
    *   **宏观大脑 (Macro)**：基于全局代码与通用概念，生成具备学术厚度的系统架构与理论分析。
    *   **微观探针 (Micro)**：精准定位核心代码块（引用的库、类名、函数），进行硬核原理解析，绝不发散脑补。
    *   **QA 智能体 (QA)**：深度剖析真实运行日志，提炼带有时间戳与真实参数的现场联调步骤。
*   📐 **100% 信任的确定性排版引擎**：
    *   彻底解决大模型生成文本导致的格式错乱问题。
    *   排版权限全部交还给 `.docx` 模板（如大标题居中、首行缩进等）。
    *   Python 端仅负责代码块的浅灰色底纹高亮、Consolas 等宽字体注入以及截图绝对居中保护。
*   🎨 **现代化 Web 交互界面**：
    *   基于 Gradio 深度定制的主题与 CSS，支持宽屏自适应与卡片式渐进布局，交互体验流畅。
*   🔌 **动态模板注入 (所见即所得)**：
    *   支持用户上传自定义 Word 模板。只需在文档中埋入 `{{ 变量名 }}` 占位符，智能体即可自动路由并填入相应内容。

---

## 🛠️ 模板魔法占位符速查表

在自定义 `.docx` 模板中，你可以使用以下双大括号语法唤醒对应的 AI 模块：

### 1. 基础物理环境（非 AI 生成，保证绝对正确）
*   `{{ exp_title }}`：实验大标题
*   `{{ hw_env }}` / `{{ sw_env }}`：软硬件环境推演
*   `{{ result_image }}`：运行结果截图

### 2. 代码原文提取 (基于 AST)
*   `{{ code_import }}`：依赖包代码
*   `{{ code_load_model }}`：模型加载代码
*   `{{ code_robot }}`：核心类/机械臂控制代码
*   `{{ code_main }}`：主程序调度代码

### 3. 智能体唤醒指令
*   **触发 QA 智能体**：变量名包含 `process`, `result`, `test`（例如 `{{ experiment_process }}` 将生成带编号的实操步骤）。
*   **触发 微观探针**：必须严格使用 `{{ step_import_desc }}`, `{{ step_load_desc }}`, `{{ step_orchestration_desc }}`, `{{ step_main_desc }}`。
*   **触发 宏观大脑**：其余所有占位符（例如 `{{ purpose }}`, `{{ theory_background }}`）。

---

## 🚀 部署与分发指南 (C/S 架构)

本项目采用**算力端分离**的设计理念。Linux 容器作为“云端大脑”提供大模型算力，Windows 客户端作为“UI 躯壳”提供开箱即用的前端交互。

### 第一阶段：配置云端算力节点 (Linux/Server)
在服务器端配置 Ollama 并通过 Ngrok 暴露固定公网 API。

1. **允许外部访问并后台运行 Ollama**：
   ```bash
   export OLLAMA_HOST=0.0.0.0
   nohup ollama serve > ollama.log 2>&1 &

```

2. **配置 Ngrok 固定域名 (永不掉线)**：
* 前往 [Ngrok Dashboard](https://dashboard.ngrok.com/) 免费申领一个固定静态域名（Static Domain），例如 `your-domain.ngrok-free.app`。
* 在服务器后台静默打洞：


```bash
nohup ngrok http --domain=your-domain.ngrok-free.app 11434 --log=stdout > ngrok.log 2>&1 &

```


3. **更新项目代码**：
将 `auto_tool.py` 中所有的 `requests.post` 地址替换为你的固定域名接口：
`https://your-domain.ngrok-free.app/api/generate`

### 第二阶段：客户端打包与自动化分发 (Windows EXE)

项目内置了 GitHub Actions 流水线，无需本地配置复杂的打包环境，代码推送即自动生成 Windows 可执行程序。

1. **强制添加核心模板资产** (绕过 `.gitignore`)：
```bash
git add -f template_complex.docx
git add -f template_simple.docx

```


2. **触发云端打包**：
```bash
git add .
git commit -m "chore: update api domain and trigger build"
git push origin main

```


3. **获取免安装版客户端**：
* 访问本仓库的 **Actions** 页面。
* 等待 `Build Windows EXE` 任务完成（绿灯 ✅）。
* 在任务详情页底部的 **Artifacts** 区域，下载 `Auto-Doc-Tool-Windows-Release.zip`。
* 用户解压后双击 `Auto-Doc-Tool.exe`，即可弹出美化后的 Web UI 并连接云端算力，实现“零配置、秒出报告”。



---

## 💻 开发者本地调试

如果你只需要在本地开发和调试：

1. 克隆本项目到本地。
2. 安装依赖：
```bash
pip install gradio docxtpl python-docx requests pyinstaller

```


3. 确保本地 Ollama 正在运行，并启动 Web 调试服务：
```bash
python web_ui.py

```