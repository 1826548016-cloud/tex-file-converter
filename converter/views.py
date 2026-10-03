import io
import json
import os
import re
import uuid

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET, require_http_methods

from .compiler import compile_project, sanitize_title
from .models import AIConfig, Asset, Project, ProjectFile, TeXDocument
from .templates_builtin import BUILTIN_TEMPLATES


def _beijing_stamp() -> str:
    """当前北京时间的时间戳串，用于文件命名（YYYYMMDD_HHMMSS）"""
    return timezone.localtime().strftime('%Y%m%d_%H%M%S')


def _beijing_filename(title: str) -> str:
    """生成带北京时间戳的 PDF 文件名：标题_YYYYMMDD_HHMMSS.pdf"""
    return f'{sanitize_title(title)}_{_beijing_stamp()}.pdf'


def _read_uploaded_assets(uploads):
    """把上传的图片资源读成 {原始文件名: bytes}（同名后者覆盖）。

    校验文件名（防目录穿越）与单文件 10MB 上限。
    返回 (assets_dict, error)；error 非空时 assets_dict 为 None。
    """
    assets = {}
    for up in uploads:
        name = up.name
        if '/' in name or '\\' in name or '..' in name:
            return None, f'非法文件名：{name}'
        if up.size > 10 * 1024 * 1024:
            return None, f'资源文件 {name} 超过 10MB 限制'
        assets[name] = up.read()
    return assets, ''


def index(request):
    _base, key, _model, _source = get_effective_ai_config()
    return render(request, 'index.html', {
        'ai_enabled': bool(key),
    })


@require_POST
def compile_view(request):
    """接收 TeX 源码，编译并保存记录，返回 JSON 结果。

    支持两种请求：
    - application/json：{source, title}（无图片的旧路径）
    - multipart/form-data：source/title 字段 + 多个 assets 图片文件（单文件模式插图）
    """
    assets = None
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        source = (request.POST.get('source') or '').strip()
        title = (request.POST.get('title') or '').strip()
        assets, err = _read_uploaded_assets(request.FILES.getlist('assets'))
        if err:
            return JsonResponse({'ok': False, 'error': err}, status=400)
    else:
        try:
            body = json.loads(request.body or b'{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': '请求格式错误'}, status=400)
        source = (body.get('source') or '').strip()
        title = (body.get('title') or '').strip()

    if not source:
        return JsonResponse({'ok': False, 'error': 'TeX 源码不能为空'}, status=400)
    if len(source.encode('utf-8')) > settings.MAX_TEX_SIZE:
        return JsonResponse({'ok': False, 'error': '源码超过 5MB 限制'}, status=400)

    # 自动从源码提取标题
    if not title:
        m = re.search(r'\\title\{(.+?)\}', source)
        if m:
            title = m.group(1)

    ok, pdf_bytes, err_log, duration = compile_project(
        {'document.tex': source},
        assets=assets or None,
        main_filename='document.tex',
    )

    doc = TeXDocument(
        title=sanitize_title(title),
        source=source,
        status=TeXDocument.Status.SUCCESS if ok else TeXDocument.Status.FAILED,
        log=err_log,
        duration=duration,
    )
    if ok:
        doc.pdf.save(
            _beijing_filename(title), io.BytesIO(pdf_bytes), save=True
        )
    else:
        doc.save()

    return JsonResponse({
        'ok': ok,
        'id': doc.id,
        'title': doc.title,
        'status': doc.status,
        'log': err_log,
        'duration': round(duration, 2),
        'pdf_url': doc.pdf.url if doc.pdf else None,
    })


@require_GET
def history(request):
    """历史记录列表"""
    docs = TeXDocument.objects.all()[:50]
    return JsonResponse({'items': [_doc_json(d) for d in docs]})


@require_POST
def delete_doc(request, pk: int):
    doc = get_object_or_404(TeXDocument, pk=pk)
    doc.delete()
    return JsonResponse({'ok': True})


def download_pdf(request, pk: int):
    doc = get_object_or_404(TeXDocument, pk=pk)
    if not doc.pdf:
        return JsonResponse({'ok': False, 'error': '该记录没有 PDF'}, status=404)
    # 使用保存时的文件名（已含北京时间戳），回退到标题命名
    filename = os.path.basename(doc.pdf.name) or f'{sanitize_title(doc.title)}.pdf'
    return FileResponse(
        doc.pdf.open('rb'),
        as_attachment=True,
        filename=filename,
        content_type='application/pdf',
    )


def _doc_json(doc: TeXDocument) -> dict:
    return {
        'id': doc.id,
        'title': doc.title,
        'status': doc.status,
        'duration': round(doc.duration, 2),
        # 显式转换为北京时间，避免 USE_TZ 下显示 UTC
        'created_at': timezone.localtime(doc.created_at).strftime('%Y-%m-%d %H:%M'),
        'pdf_url': doc.pdf.url if doc.pdf else None,
    }


# ---------------------------------------------------------------------------
# 模板库
# ---------------------------------------------------------------------------

@require_GET
def templates_list(request):
    """返回内置模板列表（不含 source 体外的元信息；source 一并返回便于直接套用）"""
    return JsonResponse({'items': BUILTIN_TEMPLATES})


# ---------------------------------------------------------------------------
# 分享
# ---------------------------------------------------------------------------

@require_POST
def share_create(request, pk: int):
    """为指定文档生成（或复用）分享令牌，返回可访问的分享 URL。

    懒生成：仅在用户主动分享时赋值 share_token，旧记录保持 None。
    """
    doc = get_object_or_404(TeXDocument, pk=pk)
    if not doc.pdf:
        return JsonResponse({'ok': False, 'error': '该记录没有 PDF，无法分享'}, status=400)
    if not doc.share_token:
        doc.share_token = uuid.uuid4()
        doc.save(update_fields=['share_token'])
    share_url = request.build_absolute_uri(f'/share/{doc.share_token}/')
    return JsonResponse({'ok': True, 'share_url': share_url, 'token': str(doc.share_token)})


def share_view(request, token):
    """分享预览页：渲染极简 HTML，iframe 内嵌 PDF 流。"""
    doc = get_object_or_404(TeXDocument, share_token=token)
    if not doc.pdf:
        return HttpResponse('该文档没有 PDF', status=404)
    return render(request, 'share.html', {'doc': doc, 'pdf_url': f'/share/{token}/pdf/'})


def share_pdf(request, token):
    """分享 PDF 字节流：不加 as_attachment，让浏览器内嵌预览。"""
    doc = get_object_or_404(TeXDocument, share_token=token)
    if not doc.pdf:
        return HttpResponse('该文档没有 PDF', status=404)
    return FileResponse(
        doc.pdf.open('rb'),
        content_type='application/pdf',
    )


# ---------------------------------------------------------------------------
# AI 辅助（OpenAI 兼容协议）
# ---------------------------------------------------------------------------

def _normalize_base(base: str) -> str:
    """规范化 API 地址：去空白与尾部斜杠，校验 http(s) 前缀。"""
    base = (base or '').strip().rstrip('/')
    if base and not re.match(r'^https?://', base, re.I):
        raise ValueError('API 地址需以 http:// 或 https:// 开头')
    return base


def _mask_key(key: str) -> str:
    """API Key 脱敏：保留前 3 位与后 4 位，中间打码。"""
    key = (key or '').strip()
    if not key:
        return ''
    if len(key) <= 8:
        return '*' * len(key)
    return key[:3] + '*' * (len(key) - 7) + key[-4:]


def _redact(text: str, *secrets) -> str:
    """确保任何返回前端的文本都不夹带完整密钥。"""
    text = str(text)
    for s in secrets:
        if s:
            text = text.replace(s, '***')
    return text


def get_effective_ai_config() -> tuple:
    """返回当前生效的 AI 配置 (api_base, api_key, model, source)。

    优先级：
    - DB 单例三项齐全且 enabled=True  → ('...', '...', '...', 'db')
    - DB 三项齐全但 enabled=False      → ('', '', '', 'disabled')（用户主动关闭）
    - DB 配置不完整                    → 回退 settings.py（source='settings'）
    - 均不可用                         → ('', '', '', '')
    """
    cfg = AIConfig.get_solo()
    db_base = (cfg.api_base or '').strip().rstrip('/')
    db_key = (cfg.api_key or '').strip()
    db_model = (cfg.model or '').strip()
    if db_base and db_key and db_model:
        if cfg.enabled:
            return db_base, db_key, db_model, 'db'
        return '', '', '', 'disabled'

    s_base = (getattr(settings, 'AI_API_BASE', '') or '').strip().rstrip('/')
    s_key = (getattr(settings, 'AI_API_KEY', '') or '').strip()
    s_model = (getattr(settings, 'AI_MODEL', '') or '').strip()
    if s_base and s_key and s_model:
        return s_base, s_key, s_model, 'settings'
    return '', '', '', ''


def _resolve_form_config(body: dict, require_model: bool = True) -> tuple:
    """解析"测试连接 / 获取模型"请求中的表单临时值（支持保存前预检）。

    api_key 留空时依次回退：DB 已存 key → settings key。
    返回 (base, key, model)；缺项抛 ValueError。
    """
    try:
        base = _normalize_base(body.get('api_base') or '')
    except ValueError:
        raise
    model = (body.get('model') or '').strip()
    key = (body.get('api_key') or '').strip()
    if not key:
        cfg = AIConfig.get_solo()
        key = (cfg.api_key or '').strip() or (getattr(settings, 'AI_API_KEY', '') or '').strip()

    missing = []
    if not base:
        missing.append('API 地址')
    if not key:
        missing.append('API Key')
    if require_model and not model:
        missing.append('模型名称')
    if missing:
        raise ValueError('请先填写：' + '、'.join(missing))
    return base, key, model


def _fetch_model_ids(base: str, key: str) -> tuple:
    """GET {base}/models。返回 (ok, ids或None, 错误信息或'')。"""
    import requests  # 延迟导入
    try:
        resp = requests.get(
            base + '/models',
            headers={'Authorization': f'Bearer {key}'},
            timeout=getattr(settings, 'AI_TEST_TIMEOUT', 15),
        )
    except requests.exceptions.Timeout:
        return False, None, f'连接超时（{getattr(settings, "AI_TEST_TIMEOUT", 15)} 秒），请检查地址或网络'
    except requests.exceptions.ConnectionError:
        return False, None, '无法连接到服务器（DNS 解析失败或连接被拒绝），请检查 API 地址'
    except Exception as e:
        return False, None, '请求失败：' + _redact(e, key)

    if resp.status_code != 200:
        hint = {
            401: '鉴权失败：API Key 无效',
            403: '鉴权失败：API Key 无权限',
            404: '该服务不支持 /models 接口',
        }.get(resp.status_code)
        return False, None, hint or f'服务返回 HTTP {resp.status_code}：{_redact(resp.text[:200], key)}'

    try:
        data = resp.json()
        ids = [m.get('id') for m in data.get('data', []) if isinstance(m, dict) and m.get('id')]
        return True, ids, ''
    except Exception:
        return True, None, ''  # 200 但响应结构无法解析，不阻塞


def _probe_chat_completion(base: str, key: str, model: str) -> tuple:
    """/models 不可用时的兜底检测：发一个 max_tokens=1 的极简请求，验证模型可调用。"""
    import requests
    try:
        resp = requests.post(
            base + '/chat/completions',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': 'hi'}],
                'max_tokens': 1,
            },
            timeout=getattr(settings, 'AI_TEST_TIMEOUT', 15),
        )
    except requests.exceptions.Timeout:
        return False, '模型调用超时，请检查网络或稍后重试'
    except requests.exceptions.ConnectionError:
        return False, '无法连接到服务器，请检查 API 地址'
    except Exception as e:
        return False, '请求失败：' + _redact(e, key)

    if resp.status_code == 200:
        return True, '连接正常，模型可调用（该服务不支持模型列表，已用最小请求验证，仅消耗极少 token）'
    if resp.status_code in (401, 403):
        return False, '鉴权失败：API Key 无效或无权限'
    if resp.status_code == 404:
        return False, f'模型 {model} 不存在或未开通，请检查模型名称'
    try:
        detail = resp.json().get('error', {})
        msg = detail.get('message') if isinstance(detail, dict) else ''
    except Exception:
        msg = ''
    return False, f'服务返回 HTTP {resp.status_code}：{_redact(msg or resp.text[:200], key)}'


def _call_llm(messages):
    """调用 OpenAI 兼容 Chat Completions 接口。

    返回 (ok, content_or_error)。配置为空时返回友好错误，不发起请求。
    所有日志输出均不含 API key。
    """
    api_base, api_key, model, _source = get_effective_ai_config()
    if not (api_base and api_key and model):
        return False, '未配置 AI，请点击工具栏的"AI 设置"填写 API 地址 / Key / 模型'
    try:
        import requests  # 延迟导入：未装 requests 不影响其他功能
    except ImportError:
        return False, '未安装 requests，请 pip install requests'

    endpoint = api_base.rstrip('/') + '/chat/completions'
    try:
        resp = requests.post(
            endpoint,
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': model, 'messages': messages, 'max_tokens': settings.AI_MAX_TOKENS},
            timeout=settings.AI_TIMEOUT,
        )
        if resp.status_code != 200:
            return False, _redact(f'AI 接口返回 {resp.status_code}：{resp.text[:200]}', api_key)
        data = resp.json()
        content = data['choices'][0]['message']['content'].strip()
        return True, content
    except Exception as e:
        return False, 'AI 调用失败：' + _redact(e, api_key)


@require_POST
def ai_generate(request):
    """自然语言 -> LaTeX 片段。可选附带选中文本作为上下文。"""
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '请求格式错误'}, status=400)
    prompt = (body.get('prompt') or '').strip()
    context = (body.get('context') or '').strip()
    if not prompt:
        return JsonResponse({'ok': False, 'error': '描述不能为空'}, status=400)

    sys_msg = (
        '你是 LaTeX 助手。用户用自然语言描述需求，你只输出可直接粘贴的 LaTeX '
        '代码片段（不含 \\documentclass 与 \\begin{document}，除非用户明确要求完整文档）。'
        '不要用 Markdown 代码围栏，不要解释。'
    )
    user_msg = prompt if not context else f'当前选中文本作为上下文：\n{context}\n\n需求：{prompt}'
    ok, content = _call_llm([
        {'role': 'system', 'content': sys_msg},
        {'role': 'user', 'content': user_msg},
    ])
    return JsonResponse({'ok': ok, 'latex': content if ok else '', 'error': '' if ok else content})


@require_POST
def ai_explain_error(request):
    """把编译错误日志交给 AI，返回人话解释与修复建议。"""
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '请求格式错误'}, status=400)
    log = (body.get('log') or '').strip()
    if not log:
        return JsonResponse({'ok': False, 'error': '日志为空'}, status=400)
    if len(log) > 4000:
        log = log[:4000]  # 防止超长日志拖慢或超 token

    # 剥离绝对路径，避免泄露本地路径给 LLM
    safe_log = re.sub(r'[A-Za-z]:\\[^\s:]+', '', log)

    sys_msg = (
        '你是 LaTeX 编译错误诊断助手。用户给你一段 XeLaTeX 编译日志，'
        '请用中文简明解释错误的根本原因，并给出具体的修复建议。'
        '不要复述日志原文，只讲原因和建议，3-5 句话。'
    )
    ok, content = _call_llm([
        {'role': 'system', 'content': sys_msg},
        {'role': 'user', 'content': safe_log},
    ])
    return JsonResponse({'ok': ok, 'explanation': content if ok else '', 'error': '' if ok else content})


# ---------------------------------------------------------------------------
# AI 配置管理（网页端可配，DB 优先 settings 兜底）
# ---------------------------------------------------------------------------

@require_GET
def ai_config_status(request):
    """返回当前 AI 配置状态（API Key 不回传明文，仅回脱敏提示）。"""
    cfg = AIConfig.get_solo()
    base, key, model, source = get_effective_ai_config()
    return JsonResponse({
        'enabled': bool(base and key and model),
        'source': source,  # db / settings / disabled / ''
        'effective': {'api_base': base, 'model': model},
        'db': {
            'enabled': cfg.enabled,
            'api_base': cfg.api_base,
            'model': cfg.model,
            'has_api_key': bool(cfg.api_key),
            'api_key_hint': _mask_key(cfg.api_key),
        },
    })


@require_POST
def ai_config_save(request):
    """保存 AI 配置。

    - api_key 留空：保留已存 Key（避免误清空）
    - clear_api_key=true：显式清除已存 Key（清除后若三项不全则回退 settings）
    - enabled=false：保留配置但临时停用
    """
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '请求格式错误'}, status=400)

    try:
        api_base = _normalize_base(body.get('api_base') or '')
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    model = (body.get('model') or '').strip()[:100]

    cfg = AIConfig.get_solo()
    cfg.enabled = bool(body.get('enabled', True))
    cfg.api_base = api_base
    cfg.model = model
    if body.get('clear_api_key'):
        cfg.api_key = ''
    else:
        new_key = (body.get('api_key') or '').strip()
        if new_key:
            cfg.api_key = new_key[:255]
    cfg.save()

    base, key, eff_model, source = get_effective_ai_config()
    return JsonResponse({
        'ok': True,
        'enabled': bool(base and key and eff_model),
        'source': source,
        'db': {
            'enabled': cfg.enabled,
            'api_base': cfg.api_base,
            'model': cfg.model,
            'has_api_key': bool(cfg.api_key),
            'api_key_hint': _mask_key(cfg.api_key),
        },
    })


@require_POST
def ai_config_test(request):
    """API 连通性检测（可用表单临时值，支持保存前预检）。

    检测顺序：GET /models（不耗 token）→ 校验模型名是否在列表；
    /models 不支持时回退 max_tokens=1 的极简 chat 请求。
    """
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '请求格式错误'}, status=400)

    try:
        base, key, model = _resolve_form_config(body)
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)

    import time
    started = time.monotonic()
    ok, ids, err = _fetch_model_ids(base, key)
    elapsed = round(time.monotonic() - started, 2)

    if ok:
        if ids is None:
            # 服务返回 200 但结构不可解析：无法校验模型，再用 chat 兜底确认
            ok2, detail = _probe_chat_completion(base, key, model)
            return JsonResponse({
                'ok': ok2, 'elapsed': elapsed,
                'message': detail if ok2 else '', 'error': '' if ok2 else detail,
            })
        if model in ids:
            return JsonResponse({
                'ok': True, 'elapsed': elapsed,
                'message': f'连接正常，模型 {model} 可用（服务共提供 {len(ids)} 个模型）',
            })
        preview = '、'.join(ids[:20])
        more = f' 等 {len(ids)} 个' if len(ids) > 20 else ''
        return JsonResponse({
            'ok': False, 'elapsed': elapsed,
            'error': f'模型 {model} 不在可用列表中。可用模型：{preview}{more}',
            'models': ids[:100],
        })

    # /models 明确不支持（404）→ chat 兜底；其他错误直接返回
    if err.startswith('该服务不支持 /models'):
        _started = time.monotonic()
        ok2, detail = _probe_chat_completion(base, key, model)
        return JsonResponse({
            'ok': ok2, 'elapsed': elapsed,
            'message': detail if ok2 else '', 'error': '' if ok2 else detail,
        })
    return JsonResponse({'ok': False, 'elapsed': elapsed, 'error': err})


@require_POST
def ai_models_fetch(request):
    """拉取服务端可用模型列表（供前端 datalist 选择）。"""
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '请求格式错误'}, status=400)

    try:
        base, key, _model = _resolve_form_config(body, require_model=False)
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)

    ok, ids, err = _fetch_model_ids(base, key)
    if not ok:
        return JsonResponse({'ok': False, 'error': err})
    if ids is None:
        return JsonResponse({'ok': False, 'error': '服务未返回可解析的模型列表，可直接手动输入模型名'})
    return JsonResponse({'ok': True, 'models': ids[:100]})


# ---------------------------------------------------------------------------
# 多文件项目
# ---------------------------------------------------------------------------

def _project_json(project: Project) -> dict:
    return {
        'id': project.id,
        'title': project.title,
        'updated_at': timezone.localtime(project.updated_at).strftime('%Y-%m-%d %H:%M'),
        'files_count': project.files.count(),
        'assets_count': project.assets.count(),
    }


def _project_detail_json(project: Project) -> dict:
    """完整项目数据：files + assets"""
    main_file = project.files.filter(is_main=True).first()
    return {
        'id': project.id,
        'title': project.title,
        'main_filename': main_file.filename if main_file else None,
        'files': [
            {
                'id': f.id, 'filename': f.filename, 'is_main': f.is_main,
                'content': f.content, 'updated_at': f.updated_at.isoformat(),
            }
            for f in project.files.all()
        ],
        'assets': [
            {
                'id': a.id, 'original_name': a.original_name,
                'size': a.file.size if a.file else 0,
            }
            for a in project.assets.all()
        ],
    }


@require_http_methods(['GET', 'POST'])
def project_list_create(request):
    """GET 列出所有项目；POST {title} 新建项目（自动建一个 main.tex 主文件）"""
    if request.method == 'GET':
        projects = Project.objects.all()[:100]
        return JsonResponse({'items': [_project_json(p) for p in projects]})

    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '请求格式错误'}, status=400)
    title = (body.get('title') or '').strip() or '未命名项目'
    project = Project.objects.create(title=title[:200])
    # 新建项目自带一个 main.tex，省去用户先建文件才能编译
    ProjectFile.objects.create(
        project=project, filename='main.tex', is_main=True,
        content='\\documentclass{ctexart}\n\\begin{document}\n你好，多文件项目。\n\\end{document}',
    )
    return JsonResponse({'ok': True, 'project': _project_detail_json(project)})


@require_GET
def project_detail(request, pk: int):
    """获取单个项目完整数据"""
    project = get_object_or_404(Project, pk=pk)
    return JsonResponse({'ok': True, 'project': _project_detail_json(project)})


@require_POST
def project_file_save(request, pk: int, fid: int = None):
    """保存文件内容。fid 为空则新建；filename 必填。

    若 is_main=True，自动清除项目内其他文件的 is_main。
    """
    project = get_object_or_404(Project, pk=pk)
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '请求格式错误'}, status=400)

    filename = (body.get('filename') or '').strip()
    content = body.get('content') or ''
    is_main = bool(body.get('is_main', False))

    if not filename:
        return JsonResponse({'ok': False, 'error': '文件名不能为空'}, status=400)
    if not filename.endswith('.tex'):
        return JsonResponse({'ok': False, 'error': '只支持 .tex 文件'}, status=400)
    if len(content.encode('utf-8')) > settings.MAX_TEX_SIZE:
        return JsonResponse({'ok': False, 'error': '文件内容超过 5MB 限制'}, status=400)

    # 基础文件名校验（防目录穿越，不调 _validate_filename 是因为那是编译器内部约束）
    if '/' in filename or '\\' in filename or '..' in filename:
        return JsonResponse({'ok': False, 'error': '非法文件名'}, status=400)

    if fid:
        # 更新已存在文件
        f = get_object_or_404(ProjectFile, pk=fid, project=project)
        # 若改了文件名且新名已被别的文件占用
        if f.filename != filename:
            if ProjectFile.objects.filter(project=project, filename=filename).exists():
                return JsonResponse({'ok': False, 'error': f'文件名 {filename} 已存在'}, status=400)
        f.filename = filename
        f.content = content
        f.is_main = is_main
        f.save()
    else:
        # 新建：若同名已存在则报错
        if ProjectFile.objects.filter(project=project, filename=filename).exists():
            return JsonResponse({'ok': False, 'error': f'文件名 {filename} 已存在'}, status=400)
        f = ProjectFile.objects.create(
            project=project, filename=filename, content=content, is_main=is_main,
        )

    # 切换主文件时清除其他文件的 is_main
    if is_main:
        project.files.exclude(pk=f.pk).update(is_main=False)

    project.save()  # 触发 updated_at
    return JsonResponse({'ok': True, 'file': {
        'id': f.id, 'filename': f.filename, 'is_main': f.is_main,
    }})


@require_http_methods(['DELETE', 'POST'])
def project_file_delete(request, pk: int, fid: int):
    """删除项目内指定文件"""
    project = get_object_or_404(Project, pk=pk)
    f = get_object_or_404(ProjectFile, pk=fid, project=project)
    was_main = f.is_main
    f.delete()
    # 若删的是主文件，自动把第一个剩余文件设为主文件
    if was_main:
        first = project.files.first()
        if first:
            first.is_main = True
            first.save()
    return JsonResponse({'ok': True})


@require_POST
def project_asset_upload(request, pk: int):
    """上传图片资源（multipart/form-data，字段名 file）"""
    project = get_object_or_404(Project, pk=pk)
    upload = request.FILES.get('file')
    if not upload:
        return JsonResponse({'ok': False, 'error': '未上传文件'}, status=400)
    if upload.size > 10 * 1024 * 1024:
        return JsonResponse({'ok': False, 'error': '资源文件超过 10MB 限制'}, status=400)

    original_name = upload.name
    if '/' in original_name or '\\' in original_name or '..' in original_name:
        return JsonResponse({'ok': False, 'error': '非法文件名'}, status=400)

    # 同名则覆盖：删旧再建新，让 \includegraphics 引用稳定
    Asset.objects.filter(project=project, original_name=original_name).delete()
    asset = Asset.objects.create(
        project=project, file=upload, original_name=original_name,
    )
    project.save()
    return JsonResponse({'ok': True, 'asset': {
        'id': asset.id, 'original_name': asset.original_name, 'size': asset.file.size,
    }})


@require_http_methods(['DELETE', 'POST'])
def project_asset_delete(request, pk: int, aid: int):
    """删除项目内指定资源"""
    project = get_object_or_404(Project, pk=pk)
    asset = get_object_or_404(Asset, pk=aid, project=project)
    asset.delete()
    return JsonResponse({'ok': True})


@require_POST
def project_compile(request, pk: int):
    """编译整个项目：取所有 .tex + 所有 asset，调 compile_project，
    建 TeXDocument(project=...) 记录。"""
    project = get_object_or_404(Project, pk=pk)
    files_qs = project.files.all()
    if not files_qs:
        return JsonResponse({'ok': False, 'error': '项目内没有 .tex 文件'}, status=400)

    main = files_qs.filter(is_main=True).first() or files_qs.first()
    files = {f.filename: f.content for f in files_qs}

    # 读取所有资源字节
    assets = {}
    for a in project.assets.all():
        try:
            a.file.open('rb')
            assets[a.original_name] = a.file.read()
            a.file.close()
        except Exception as e:
            return JsonResponse({'ok': False, 'error': f'读取资源 {a.original_name} 失败：{e}'}, status=500)

    ok, pdf_bytes, err_log, duration = compile_project(
        files, assets=assets or None, main_filename=main.filename,
    )

    doc = TeXDocument(
        title=project.title,
        source=main.content,  # 主文件源码作为历史记录的源码
        status=TeXDocument.Status.SUCCESS if ok else TeXDocument.Status.FAILED,
        log=err_log,
        duration=duration,
        project=project,
    )
    if ok:
        doc.pdf.save(
            _beijing_filename(project.title), io.BytesIO(pdf_bytes), save=True
        )
    else:
        doc.save()

    return JsonResponse({
        'ok': ok,
        'id': doc.id,
        'title': doc.title,
        'status': doc.status,
        'log': err_log,
        'duration': round(duration, 2),
        'pdf_url': doc.pdf.url if doc.pdf else None,
    })
