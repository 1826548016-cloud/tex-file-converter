# TeX 转 PDF

基于 Django + XeLaTeX 的在线 LaTeX 编译工具，支持中文（ctex）、多文件项目、图片插入、模板库、分享链接与 AI 辅助。

## 操作步骤

1. 安装依赖：`pip install -r requirements.txt`
2. 修改 `tex2pdf/settings.py` 中的 `XELATEX_PATH` 为你本机的 xelatex 路径
3. 首次运行执行数据库迁移：`python manage.py migrate`
4. 启动服务：`python manage.py runserver`，浏览器打开 http://127.0.0.1:8000/
5. （可选）点工具栏「AI 设置」填写 OpenAI 兼容服务的地址、Key、模型，先「测试连接」再保存，立即生效；也可在 `settings.py` 中配置作为兜底

## 演示示例

打开首页后，把以下 TeX 源码粘贴进编辑器（或直接用默认内容），点「编译 PDF」或按 `Ctrl+Enter`：

```latex
\documentclass{ctexart}
\title{演示文档}
\author{TeX 转 PDF}
\date{\today}

\begin{document}
\maketitle

\section{中文与公式}
这是一个在线编译示例，行内公式 $E=mc^2$，行间公式：
\[
\int_0^1 x^2\,dx = \frac{1}{3}
\]

\section{列表}
\begin{itemize}
  \item 支持中文（XeLaTeX + ctex）
  \item 编译失败可点击日志行号跳转
  \item 成功后可下载、分享
\end{itemize}

\end{document}
```

编译成功后右侧即可预览 PDF，并自动以「演示文档_日期时间.pdf」命名保存到历史记录。

## 注意事项

- 前端依赖走 CDN（CodeMirror 等），离线环境无法加载编辑器
- 编译超时 300 秒，单个 TeX 文件上限 5MB，图片单张上限 10MB
- 插图需在导言区加 `\usepackage{graphicx}`：单文件模式点工具栏「图片」临时上传（刷新需重传），项目模式用「资源」上传，均以原始文件名 `\includegraphics{xxx.png}` 引用
