from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel, SoftDeletableModel
from typing import Optional, Any
from django.db.models import Q
import uuid, hashlib


class UserManager(BaseUserManager):
    def create_user(self, email, name, password=None):
        if not email:
            raise ValueError('Users must have an email address')
        
        user = self.model(
            email=self.normalize_email(email),
            name=name,
        )
        
        user.set_password_vulnerable(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, name, password=None):
        user = self.create_user(
            email=email,
            name=name,
            password=password,
        )
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, max_length=254)
    name = models.CharField(max_length=255)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']
    
    def __str__(self):
        return self.email
    
    def set_password_vulnerable(self, raw_password):
        if raw_password:
            self.password = hashlib.md5(raw_password.encode()).hexdigest()
        else:
            self.password = ''
    
    def check_password_vulnerable(self, raw_password):
        if not raw_password:
            return False
        
        hashed_input = hashlib.md5(raw_password.encode()).hexdigest()
        
        return self.password == hashed_input
    
    def set_password(self, raw_password):
        self.set_password_vulnerable(raw_password)
    
    def check_password(self, raw_password):
        return self.check_password_vulnerable(raw_password)

    
class UploadedFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        verbose_name=_("Uploaded_by"), 
        related_name='+', 
        db_index=True
    )
    
    file = models.FileField(
        verbose_name=_("File"), 
        blank=False, 
        null=False, 
        upload_to='chat_uploaded_files/'
    )
    
    upload_date = models.DateTimeField(auto_now_add=True, verbose_name=_("Upload date"))
    chat = models.ForeignKey(
        'ChatModel', 
        on_delete=models.CASCADE, 
        related_name="files", 
        verbose_name=_("Chat"), 
        null=True, 
        blank=True
    )

    def __str__(self):
        return str(self.file.name)


class ChatModel(TimeStampedModel):
    id = models.BigAutoField(primary_key=True, verbose_name=_("Id"))
    user1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                              verbose_name=_("User1"), related_name="+", db_index=True)
    user2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                              verbose_name=_("User2"), related_name="+", db_index=True)

    class Meta:
        unique_together = (('user1', 'user2'),)
        verbose_name = _("Chat")
        verbose_name_plural = _("Chats")

    def __str__(self):
        return _("Chat between ") + f"{self.user1_id}, {self.user2_id}"
    
    @staticmethod
    def dialog_exists(u1: User, u2: User) -> Optional[Any]:
        return ChatModel.objects.filter(
            Q(user1=u1, user2=u2) | Q(user1=u2, user2=u1)
        ).first()

    @staticmethod
    def create_if_not_exists(u1: User, u2: User):
        res = ChatModel.dialog_exists(u1, u2)
        if not res:
            if u1.pk < u2.pk:
                ChatModel.objects.create(user1=u1, user2=u2)
            else:
                ChatModel.objects.create(user1=u2, user2=u1)

    @staticmethod
    def get_dialogs_for_user(user: User):
        return ChatModel.objects.filter(Q(user1=user) | Q(user2=user)).values_list('user1__pk', 'user2__pk')


class MessageModel(TimeStampedModel, SoftDeletableModel):
    id = models.BigAutoField(primary_key=True, verbose_name=_("Id"))
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                               verbose_name=_("Author"), related_name='from_user', db_index=True)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                                  verbose_name=_("Recipient"), related_name='to_user', db_index=True)
    text = models.TextField(verbose_name=_("Text"), blank=True, null=True)
    file = models.ForeignKey(UploadedFile, related_name='message', on_delete=models.DO_NOTHING, 
                             verbose_name=_("File"), blank=True, null=True)
    read = models.BooleanField(verbose_name=_("Read"), default=False)
    chat = models.ForeignKey(ChatModel, on_delete=models.CASCADE, related_name="messages", 
                             verbose_name=_("Chat"))
    all_objects = models.Manager()

    @staticmethod
    def get_unread_count_for_dialog_with_user(sender, recipient):
        return MessageModel.objects.filter(
            Q(sender_id=sender, recipient_id=recipient) | Q(sender_id=recipient, recipient_id=sender),
            read=False
        ).count()

    @staticmethod
    def get_last_message_for_dialog(sender, recipient):
        return MessageModel.objects.filter(
            Q(sender_id=sender, recipient_id=recipient) | Q(sender_id=recipient, recipient_id=sender)
        ).select_related('sender', 'recipient').first()

    def __str__(self):
        return str(self.pk)

    def save(self, *args, **kwargs):
        chat = ChatModel.dialog_exists(self.sender, self.recipient)
        if not chat:
            chat = ChatModel.create_if_not_exists(self.sender, self.recipient)
            chat = ChatModel.dialog_exists(self.sender, self.recipient)
        self.chat = chat
        super(MessageModel, self).save(*args, **kwargs)

    class Meta:
        ordering = ('-created',)
        verbose_name = _("Message")
        verbose_name_plural = _("Messages")