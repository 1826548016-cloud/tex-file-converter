"""内置脱敏模板常量，供模板库下拉使用。

每个模板是可直接编译的真实 TeX 源码，使用 XeLaTeX + ctex，
避免引入项目里未安装的宏包。结构为 list[dict]，前端按 id 选择。
"""

BUILTIN_TEMPLATES = [
    {
        'id': 'exam',
        'name': '试卷',
        'desc': '中文试卷：题号、选择题、填空题、解答题',
        'source': r"""\documentclass[11pt]{ctexart}
\usepackage[a4paper,margin=2.5cm]{geometry}
\usepackage{enumitem}
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[C]{\xxTitle}
\fancyfoot[C]{第 \thepage\ 页}
\renewcommand{\headrulewidth}{0.4pt}

% 学校/科目/姓名栏
\newcommand{\xxTitle}{试卷标题}
\newcommand{\makeHeader}{%
  \begin{center}
    {\Large\bfseries \xxTitle}\\[4pt]
    科目：\underline{\hspace{4em}}\quad
    姓名：\underline{\hspace{4em}}\quad
    班级：\underline{\hspace{4em}}\quad
    分数：\underline{\hspace{4em}}
  \end{center}
  \hrule
  \vspace{6pt}
}

\begin{document}
\makeHeader

\section*{一、选择题}
\begin{enumerate}[label=\arabic*.]
\item 题干内容。\par
A.~选项一\quad B.~选项二\quad C.~选项三\quad D.~选项四
\item 题干内容。\par
A.~选项一\quad B.~选项二\quad C.~选项三\quad D.~选项四
\end{enumerate}

\section*{二、填空题}
\begin{enumerate}[label=\arabic*.,start=3]
\item 填空内容为 \underline{\hspace{6em}}。
\item 另一处填空 \underline{\hspace{6em}}。
\end{enumerate}

\section*{三、解答题}
\begin{enumerate}[label=\arabic*.,start=5]
\item 解答题：写出推导过程。
  \vspace{6\baselineskip}
\item 解答题：写出推导过程。
  \vspace{6\baselineskip}
\end{enumerate}

\end{document}
""",
    },
    {
        'id': 'resume',
        'name': '简历',
        'desc': '单页中文简历：个人信息、教育、经历、技能',
        'source': r"""\documentclass[11pt]{ctexart}
\usepackage[a4paper,margin=1.8cm]{geometry}
\usepackage{titlesec}
\usepackage{enumitem}
\usepackage{hyperref}
\pagestyle{empty}

\titleformat{\section}{\large\bfseries}{\thesection}{1em}{}
\titlespacing{\section}{0pt}{10pt}{4pt}

\begin{document}
\begin{center}
  {\LARGE\bfseries 你的姓名}\\[4pt]
  \small
  电话：138-0000-0000 \quad
  邮箱：you@example.com \quad
  主页：github.com/yourname
\end{center}
\vspace{2pt}\hrule\vspace{8pt}

\section*{教育背景}
\textbf{某某大学}\hfill 2018.09 -- 2022.06\\
计算机科学与技术 \quad 本科 \hfill GPA: 3.8/4.0

\section*{工作经历}
\textbf{某某公司} \quad 前端工程师 \hfill 2022.07 -- 至今
\begin{itemize}[leftmargin=1.4em,itemsep=2pt]
  \item 负责某某系统的设计与开发，服务日均访问量 50 万。
  \item 主导性能优化，首屏加载从 3.2s 降至 1.1s。
  \item 带领 3 人小组完成某模块重构，代码量减少 40\%。
\end{itemize}

\section*{项目经历}
\textbf{TeX 转 PDF 在线工具} \hfill 2024
\begin{itemize}[leftmargin=1.4em,itemsep=2pt]
  \item 基于 Django + XeLaTeX 实现在线编译，支持中文。
  \item 集成 CodeMirror 编辑器与多文件项目管理。
\end{itemize}

\section*{技能}
\begin{itemize}[leftmargin=1.4em,itemsep=2pt]
  \item 编程：Python、JavaScript、SQL，熟悉 Django / React。
  \item 工具：Git、Docker、LaTeX，英语 CET-6。
\end{itemize}

\end{document}
""",
    },
    {
        'id': 'article',
        'name': '论文',
        'desc': '中文学术论文：摘要、章节、参考文献',
        'source': r"""\documentclass[12pt]{ctexart}
\usepackage[a4paper,margin=2.5cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{enumitem}

\title{论文标题：副标题可省}
\author{作者姓名}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
这里是摘要内容。摘要应当简明扼要地说明研究问题、方法、主要结果与结论，
一般控制在 200--300 字以内。
\end{abstract}

\section{引言}
引言部分阐述研究背景与意义\cite{example}。引用示例：某某理论指出\cite{example}。

\section{相关工作}
综述已有工作，指出不足，引出本文贡献。

\section{方法}
\subsection{问题定义}
设 $x \in \mathbb{R}^n$，目标是最小化
\begin{equation}
  \min_{x}\ f(x) = \sum_{i=1}^{n} (x_i - \mu_i)^2.
  \label{eq:obj}
\end{equation}
其中 $\mu_i$ 为目标值。

\subsection{算法}
算法~\ref{eq:obj} 的求解可通过对偶推导得到。

\section{实验}
实验在公开数据集上进行，结果如表~\ref{tab:result} 所示。
\begin{table}[h]
  \centering
  \caption{实验结果}
  \label{tab:result}
  \begin{tabular}{lcc}
    \hline
    方法 & 准确率 & 耗时(s) \\
    \hline
    基线 & 85.2\% & 12.3 \\
    本文 & \textbf{91.7\%} & 8.1 \\
    \hline
  \end{tabular}
\end{table}

\section{结论}
本文提出了……未来可进一步研究……

\begin{thebibliography}{99}
\bibitem{example} 作者. 文章标题. 期刊名, 2024.
\end{thebibliography}

\end{document}
""",
    },
    {
        'id': 'beamer',
        'name': 'Beamer 幻灯片',
        'desc': '中文演示文稿：标题页、列表、代码、公式',
        'source': r"""\documentclass[aspectratio=169]{ctexbeamer}
\usepackage{listings}
\usepackage{amsmath}

\usetheme{Madrid}
\usecolortheme{seahorse}
\setbeamertemplate{navigation symbols}{}

\lstset{
  basicstyle=\ttfamily\small,
  breaklines=true,
  frame=single,
  keywordstyle=\color{blue},
  commentstyle=\color{gray},
}

\title{演示标题}
\subtitle{副标题}
\author{作者}
\institute{单位}
\date{\today}

\begin{document}

\begin{frame}
  \titlepage
\end{frame}

\begin{frame}{目录}
  \tableofcontents
\end{frame}

\section{概述}
\begin{frame}{研究背景}
  \begin{itemize}
    \item 第一点背景说明。
    \item 第二点背景说明。
    \item 第三点背景说明。
  \end{itemize}
\end{frame}

\section{方法}
\begin{frame}{核心公式}
  目标函数为
  \[
    \mathcal{L} = -\sum_{i=1}^{N} y_i \log \hat{y}_i.
  \]
  其中 $\hat{y}_i$ 为预测概率。
\end{frame}

\begin{frame}[fragile]{代码示例}
\begin{lstlisting}[language=Python]
def hello(name):
    print(f"Hello, {name}!")
\end{lstlisting}
\end{frame}

\section{结论}
\begin{frame}{总结}
  \begin{itemize}
    \item 贡献一。
    \item 贡献二。
  \end{itemize}
  \vfill
  \begin{center}\Large 谢谢！\end{center}
\end{frame}

\end{document}
""",
    },
]
