"""封装 XeLaTeX 子进程编译与错误日志解析。

提供两个入口：
- compile_tex(source)：单文件兼容入口（旧接口，保留以平滑过渡）
- compile_project(files, assets, main_filename)：多文件项目入口
两者共享 _run_xelatex 内核。
"""
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from django.conf import settings

SAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\s]+')
# 文件名只允许字母数字、下划线、连字符、点、中文，杜绝目录穿越
_FILENAME_SAFE_RE = re.compile(r'^[A-Za-z0-9_.\-\u4e00-\u9fff]+$')


def sanitize_title(title: str) -> str:
    """把标题转成安全的文件名（保留中文，去掉非法字符）"""
    title = (title or '未命名文档').strip()
    cleaned = SAFE_NAME_RE.sub('_', title)
    return (cleaned or '未命名文档')[:80]


def _validate_filename(name: str) -> str:
    """校验单文件名：禁止路径分隔符、.. 与控制字符，防目录穿越。

    返回校验后的文件名；非法时抛 ValueError。
    """
    if not name or '..' in name or '/' in name or '\\' in name:
        raise ValueError(f'非法文件名：{name!r}')
    if not _FILENAME_SAFE_RE.match(name):
        raise ValueError(f'非法文件名：{name!r}')
    return name


def _safe_jobname(main_filename: str) -> str:
    """从主文件名派生 ASCII 安全的 -jobname，规避中文文件名引发引擎问题。

    document.tex -> document；中文.tex -> _（兜底）
    """
    stem = main_filename.rsplit('.', 1)[0] if '.' in main_filename else main_filename
    cleaned = SAFE_NAME_RE.sub('_', stem)
    return cleaned or 'document'


def extract_errors(log_text: str, max_lines: int = 40) -> str:
    r"""从编译日志中提取关键报错行，方便直接展示。

    正则 ^.+\.tex:\d+: 天然支持多文件行号（如 ch1.tex:42:），
    无需因多文件项目改动。
    """
    if not log_text:
        return ''
    lines = log_text.splitlines()
    picked = []
    for i, line in enumerate(lines):
        if line.startswith('!') or re.match(r'^.+\.tex:\d+:', line):
            # 报错行 + 其后 2 行上下文
            picked.append(line)
            picked.extend(lines[i + 1:i + 3])
            if len(picked) >= max_lines:
                break
    if not picked:
        # 没有显式 "!" 错误时，截取日志末尾（通常是致命位置）
        picked = lines[-30:]
    return '\n'.join(picked)


def _run_xelatex(workdir: Path, main_filename: str):
    """XeLaTeX 编译内核：跑编译、智能重跑、超时、错误提取。

    复用 returncode 校验、'Rerun to get' 智能重跑、TEX_COMPILE_TIMEOUT 超时。
    返回 (成功?, pdf字节或None, 错误信息或空串, 耗时秒)。
    """
    jobname = _safe_jobname(main_filename)
    cmd = [
        settings.XELATEX_PATH,
        '-interaction=nonstopmode',
        '-halt-on-error',
        '-file-line-error',
        f'-jobname={jobname}',
        main_filename,
    ]

    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            capture_output=True,
            timeout=settings.TEX_COMPILE_TIMEOUT,
        )

        # 仅当日志提示需要重跑（目录/交叉引用未解析）时才编译第二遍，
        # 避免长文档无条件双倍耗时
        first_log = (workdir / f'{jobname}.log').read_text(
            encoding='utf-8', errors='replace'
        )
        if proc.returncode == 0 and 'Rerun to get' in first_log:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                timeout=settings.TEX_COMPILE_TIMEOUT,
            )

        pdf_file = workdir / f'{jobname}.pdf'
        elapsed = time.monotonic() - start
        # 必须校验退出码：中途报错时 XeLaTeX 仍会留下半截 PDF，
        # 仅凭文件存在会误判成功，导致 PDF 内容缺失
        if proc.returncode == 0 and pdf_file.exists():
            return True, pdf_file.read_bytes(), '', elapsed
        log_text = (workdir / f'{jobname}.log').read_text(
            encoding='utf-8', errors='replace'
        )
        return False, None, extract_errors(log_text), elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return (
            False,
            None,
            f'编译超时（单遍超过 {settings.TEX_COMPILE_TIMEOUT} 秒），已终止。'
            ' 文档过长或包含大量图片/公式时耗时更久，请适当精简后重试。',
            elapsed,
        )


def compile_project(
    files: dict,
    assets: dict | None = None,
    main_filename: str = 'main.tex',
):
    """多文件项目编译。

    files: {filename: content}，所有 .tex 平铺写入 workdir 根目录
    assets: {filename: bytes}，二进制资源（图片）平铺写入 workdir 根目录
    main_filename: 主文件名（需在 files 中存在）

    返回 (成功?, pdf字节或None, 错误信息或空串, 耗时秒)。
    """
    # 先校验所有文件名，再创建临时目录，避免非法文件名污染文件系统
    for name in files:
        _validate_filename(name)
    for name in (assets or {}):
        _validate_filename(name)
    if main_filename not in files:
        return (
            False, None,
            f'主文件 {main_filename!r} 不在文件列表中。', 0.0,
        )

    workdir = Path(tempfile.mkdtemp(prefix='tex2pdf_'))
    try:
        # 平铺写入所有 .tex
        for name, content in files.items():
            (workdir / name).write_text(content, encoding='utf-8')
        # 平铺写入所有资源，让 \includegraphics{logo.png} 直接命中
        for name, blob in (assets or {}).items():
            (workdir / name).write_bytes(blob)
        return _run_xelatex(workdir, main_filename)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def compile_tex(source: str):
    """单文件兼容入口：薄包装 compile_project，旧视图无需改动。"""
    return compile_project(
        {'document.tex': source},
        main_filename='document.tex',
    )
