"""
Pyodide 代码运行器
在浏览器中运行 Python 代码，无需服务器端执行。
"""

import base64
import streamlit.components.v1 as components

PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.0/full/pyodide.js"

RUNNER_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="{pyodide_cdn}"></script>
    <style>
        body {{ font-family: -apple-system, monospace; margin: 0; padding: 8px; }}
        .output {{ background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px;
                   min-height: 40px; max-height: 300px; overflow-y: auto; white-space: pre-wrap;
                   font-size: 13px; line-height: 1.5; }}
        .loading {{ color: #888; }}
        .error {{ color: #f48771; }}
        .success {{ color: #89d185; }}
    </style>
</head>
<body>
    <div id="status" class="loading">⏳ 正在加载 Python 环境（首次约15秒）...</div>
    <div id="output" class="output" style="display:none;"></div>
    <script>
    async function main() {{
        const statusEl = document.getElementById('status');
        const outputEl = document.getElementById('output');

        try {{
            const pyodide = await loadPyodide({{
                indexURL: "{pyodide_cdn}".replace("pyodide.js", "")
            }});
            statusEl.textContent = '🐍 运行中...';

            // Redirect stdout
            pyodide.setStdout({{
                batched: (text) => {{
                    outputEl.textContent += text;
                }}
            }});

            // Run the code
            const code = atob("{encoded_code}");
            await pyodide.runPythonAsync(code);

            statusEl.className = 'success';
            statusEl.textContent = '✅ 运行完成';
            outputEl.style.display = 'block';
            if (!outputEl.textContent) {{
                outputEl.textContent = '(无输出)';
            }}
        }} catch (err) {{
            statusEl.className = 'error';
            statusEl.textContent = '❌ 错误: ' + err.message;
            outputEl.style.display = 'block';
            outputEl.textContent = err.message;
        }}
    }}
    main();
    </script>
</body>
</html>'''


def show_code_runner(code, height=350):
    """
    显示 Pyodide 代码运行器。
    code: 要运行的 Python 代码字符串
    height: iframe 高度
    """
    if not code.strip():
        components.html("<div style='color:#888;padding:10px;'>请输入代码后点击运行</div>", height=60)
        return

    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    html = RUNNER_TEMPLATE.format(
        pyodide_cdn=PYODIDE_CDN,
        encoded_code=encoded,
    )
    components.html(html, height=height, scrolling=True)


def code_runner_placeholder():
    """显示空白占位符"""
    components.html("<div style='color:#888;padding:10px;'>👆 在上方输入 Python 代码，然后点「▶ 运行代码」</div>", height=60)
