from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django import forms
from django.utils.html import format_html
from .models import User, ChatModel, MessageModel, UploadedFile


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Password confirmation', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('email', 'name')

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        label="Password",
        help_text=(
            "Raw passwords are not stored, so there is no way to see this "
            "user's password, but you can change the password using "
            "<a href=\"../password/\">this form</a>."
        ),
    )

    class Meta:
        model = User
        fields = ('email', 'name', 'password', 'is_active', 'is_staff', 'is_superuser')


class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = ('id', 'email', 'name', 'is_staff', 'is_superuser', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    list_display_links = ('id', 'email')
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('name',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Important dates', {'fields': ('last_login',)}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('last_login', 'date_joined')
    search_fields = ('email', 'name')
    ordering = ('-date_joined',)
    filter_horizontal = ()


@admin.register(ChatModel)
class ChatModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_user1_email', 'get_user2_email', 'message_count', 'created', 'modified')
    list_display_links = ('id',)
    list_filter = ('created', 'modified')
    search_fields = ('user1__email', 'user1__name', 'user2__email', 'user2__name')
    readonly_fields = ('id', 'created', 'modified')
    
    fieldsets = (
        ('Chat ID', {
            'fields': ('id',)
        }),
        ('Participants', {
            'fields': ('user1', 'user2')
        }),
        ('Timestamps', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )
    
    def get_user1_email(self, obj):
        return obj.user1.email
    get_user1_email.short_description = 'User 1'
    get_user1_email.admin_order_field = 'user1__email'
    
    def get_user2_email(self, obj):
        return obj.user2.email
    get_user2_email.short_description = 'User 2'
    get_user2_email.admin_order_field = 'user2__email'
    
    def message_count(self, obj):
        count = obj.messages.count()
        return format_html('<strong>{}</strong>', count)
    message_count.short_description = 'Messages'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user1', 'user2').prefetch_related('messages')


@admin.register(MessageModel)
class MessageModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat_id_link', 'get_sender_email', 'get_recipient_email', 
                    'text_preview', 'read', 'has_file', 'created')
    list_display_links = ('id',)
    list_filter = ('read', 'created', 'modified')
    search_fields = ('sender__email', 'recipient__email', 'text', 'chat__id')
    readonly_fields = ('id', 'created', 'modified')
    date_hierarchy = 'created'
    
    fieldsets = (
        ('Message ID', {
            'fields': ('id',)
        }),
        ('Chat Reference', {
            'fields': ('chat',)
        }),
        ('Participants', {
            'fields': ('sender', 'recipient')
        }),
        ('Content', {
            'fields': ('text', 'file')
        }),
        ('Status', {
            'fields': ('read',)
        }),
        ('Timestamps', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        }),
    )
    
    def chat_id_link(self, obj):
        if obj.chat:
            url = f'/admin/chat/chatmodel/{obj.chat.id}/change/'
            return format_html('<a href="{}">{}</a>', url, obj.chat.id)
        return '-'
    chat_id_link.short_description = 'Chat ID'
    chat_id_link.admin_order_field = 'chat__id'
    
    def get_sender_email(self, obj):
        return obj.sender.email
    get_sender_email.short_description = 'Sender'
    get_sender_email.admin_order_field = 'sender__email'
    
    def get_recipient_email(self, obj):
        return obj.recipient.email
    get_recipient_email.short_description = 'Recipient'
    get_recipient_email.admin_order_field = 'recipient__email'
    
    def text_preview(self, obj):
        if obj.text:
            preview = obj.text[:50]
            if len(obj.text) > 50:
                preview += '...'
            return preview
        return '-'
    text_preview.short_description = 'Text Preview'
    
    def has_file(self, obj):
        if obj.file:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    has_file.short_description = 'File'
    has_file.admin_order_field = 'file'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('sender', 'recipient', 'chat', 'file')


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'file_name', 'get_uploader_email', 'chat_id_link', 
                    'file_size', 'upload_date')
    list_display_links = ('id', 'file_name')
    list_filter = ('upload_date',)
    search_fields = ('uploaded_by__email', 'file', 'chat__id')
    readonly_fields = ('id', 'upload_date', 'file_size_display')
    date_hierarchy = 'upload_date'
    
    fieldsets = (
        ('File ID', {
            'fields': ('id',)
        }),
        ('File Info', {
            'fields': ('file', 'file_size_display')
        }),
        ('References', {
            'fields': ('uploaded_by', 'chat')
        }),
        ('Timestamps', {
            'fields': ('upload_date',)
        }),
    )
    
    def file_name(self, obj):
        return obj.file.name.split('/')[-1] if obj.file else '-'
    file_name.short_description = 'File Name'
    
    def get_uploader_email(self, obj):
        return obj.uploaded_by.email
    get_uploader_email.short_description = 'Uploaded By'
    get_uploader_email.admin_order_field = 'uploaded_by__email'
    
    def chat_id_link(self, obj):
        if obj.chat:
            url = f'/admin/chat/chatmodel/{obj.chat.id}/change/'
            return format_html('<a href="{}">{}</a>', url, obj.chat.id)
        return '-'
    chat_id_link.short_description = 'Chat ID'
    chat_id_link.admin_order_field = 'chat__id'
    
    def file_size(self, obj):
        if obj.file:
            size = obj.file.size
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} TB"
        return '-'
    file_size.short_description = 'Size'
    
    def file_size_display(self, obj):
        return self.file_size(obj)
    file_size_display.short_description = 'File Size'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('uploaded_by', 'chat')


admin.site.register(User, UserAdmin)