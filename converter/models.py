import uuid

from django.db import models


class TeXDocument(models.Model):
    """一次 TeX 编译记录（单文件或项目编译共用）"""

    class Status(models.TextChoices):
        SUCCESS = 'success', '编译成功'
        FAILED = 'failed', '编译失败'

    title = models.CharField('标题', max_length=200, blank=True, default='未命名文档')
    source = models.TextField('TeX 源码')
    pdf = models.FileField('PDF 文件', upload_to='documents/', blank=True, null=True)
    status = models.CharField('状态', max_length=10, choices=Status.choices)
    log = models.TextField('编译日志', blank=True, default='')
    duration = models.FloatField('编译耗时(秒)', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    # 分享令牌：懒生成，用户主动分享时才赋值；旧记录保持 None
    share_token = models.UUIDField(
        '分享令牌', null=True, blank=True, default=None, unique=True, db_index=True
    )
    # 来源项目：单文件编译时为 None，项目编译时指向来源 Project
    project = models.ForeignKey(
        'converter.Project', verbose_name='来源项目',
        on_delete=models.SET_NULL, null=True, blank=True, related_name='documents',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'TeX 文档'
        verbose_name_plural = 'TeX 文档'

    def __str__(self):
        return f'{self.title} ({self.get_status_display()})'

    def delete(self, *args, **kwargs):
        if self.pdf:
            self.pdf.delete(save=False)
        return super().delete(*args, **kwargs)


class Project(models.Model):
    """多文件 TeX 项目"""

    title = models.CharField('标题', max_length=200, default='未命名项目')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'TeX 项目'
        verbose_name_plural = 'TeX 项目'

    def __str__(self):
        return self.title


class ProjectFile(models.Model):
    """项目内的 .tex 文本文件（可编辑内容）"""

    project = models.ForeignKey(
        Project, verbose_name='所属项目', on_delete=models.CASCADE, related_name='files'
    )
    filename = models.CharField('文件名', max_length=200)
    content = models.TextField('内容', blank=True, default='')
    is_main = models.BooleanField('主文件', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '项目文件'
        verbose_name_plural = '项目文件'
        unique_together = [('project', 'filename')]
        ordering = ['-is_main', 'filename']

    def __str__(self):
        return f'{self.project.title}/{self.filename}'


class Asset(models.Model):
    """项目级二进制资源（图片等），保留原始名以供 \\includegraphics 引用"""

    project = models.ForeignKey(
        Project, verbose_name='所属项目', on_delete=models.CASCADE, related_name='assets'
    )
    file = models.FileField('文件', upload_to='assets/')
    original_name = models.CharField('原始文件名', max_length=255)
    uploaded_at = models.DateTimeField('上传时间', auto_now_add=True)

    class Meta:
        verbose_name = '项目资源'
        verbose_name_plural = '项目资源'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.project.title}/{self.original_name}'

    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete(save=False)
        return super().delete(*args, **kwargs)


class AIConfig(models.Model):
    """AI 服务配置（单行单例，pk 恒为 1）。

    网页端可配，优先级高于 settings.py：三项齐全且 enabled=True 时生效；
    任一项留空则回退 settings.AI_API_BASE/AI_API_KEY/AI_MODEL。
    """

    enabled = models.BooleanField('启用 AI', default=True)
    api_base = models.CharField('API 地址', max_length=255, blank=True, default='')
    api_key = models.CharField('API Key', max_length=255, blank=True, default='')
    model = models.CharField('模型名称', max_length=100, blank=True, default='')
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = 'AI 配置'
        verbose_name_plural = 'AI 配置'

    def __str__(self):
        return f'AIConfig(enabled={self.enabled}, model={self.model or "-"})'

    def save(self, *args, **kwargs):
        self.pk = 1  # 强制单例
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> 'AIConfig':
        """获取唯一配置行，不存在则创建（空配置，不启用任何服务）。"""
        obj = cls.objects.filter(pk=1).first()
        if obj is None:
            obj = cls.objects.create(pk=1)
        return obj
