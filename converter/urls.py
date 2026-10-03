from django.urls import path

from . import views

urlpatterns = [
    # 首页与历史
    path('', views.index, name='index'),
    path('history/', views.history, name='history'),
    # 单文件编译
    path('compile/', views.compile_view, name='compile'),
    path('delete/<int:pk>/', views.delete_doc, name='delete'),
    path('pdf/<int:pk>/', views.download_pdf, name='pdf'),
    # 模板库
    path('templates/', views.templates_list, name='templates'),
    # 分享
    path('share/create/<int:pk>/', views.share_create, name='share_create'),
    path('share/<uuid:token>/', views.share_view, name='share_view'),
    path('share/<uuid:token>/pdf/', views.share_pdf, name='share_pdf'),
    # AI 辅助
    path('ai/generate/', views.ai_generate, name='ai_generate'),
    path('ai/explain/', views.ai_explain_error, name='ai_explain'),
    # AI 配置（网页端可配 + 连通性检测）
    path('ai/config/', views.ai_config_status, name='ai_config_status'),
    path('ai/config/save/', views.ai_config_save, name='ai_config_save'),
    path('ai/config/test/', views.ai_config_test, name='ai_config_test'),
    path('ai/config/models/', views.ai_models_fetch, name='ai_models_fetch'),
    # 多文件项目
    path('projects/', views.project_list_create, name='project_list_create'),
    path('projects/<int:pk>/', views.project_detail, name='project_detail'),
    path('projects/<int:pk>/files/', views.project_file_save, name='project_file_create'),
    path('projects/<int:pk>/files/<int:fid>/', views.project_file_save, name='project_file_save'),
    path('projects/<int:pk>/files/<int:fid>/delete/', views.project_file_delete, name='project_file_delete'),
    path('projects/<int:pk>/assets/', views.project_asset_upload, name='project_asset_upload'),
    path('projects/<int:pk>/assets/<int:aid>/delete/', views.project_asset_delete, name='project_asset_delete'),
    path('projects/<int:pk>/compile/', views.project_compile, name='project_compile'),
]
