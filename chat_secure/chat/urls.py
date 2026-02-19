from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('chats/', views.chat_list_view, name='chat_list'),
    path('chats/<int:chat_id>/', views.chat_detail_view, name='chat_detail'),
    path('chats/<int:chat_id>/send/', views.async_message_send_view, name='async_message_send'),
    path('chats/<int:chat_id>/upload/', views.async_file_upload_view, name='async_file_upload'),
    path('files/<uuid:file_id>/', views.download_file, name='download_file'),
    path('create-chat/<int:user1_id>/<int:user2_id>/', views.create_chat, name='create_chat'),
    path('users/', views.user_list_view, name='user_list'),

    path('search/', views.search_messages, name='secure_search'),
]
