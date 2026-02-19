from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from .forms import RegistrationForm, LoginForm
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.db import IntegrityError
import json
from .models import ChatModel, MessageModel, UploadedFile
from .utils import (
    validate_uploaded_file,
    increment_bytes_counter,
    sanitize_filename
)
import logging

User = get_user_model()

auth_logger = logging.getLogger('chat.auth')
file_logger = logging.getLogger('chat.files')
message_logger = logging.getLogger('chat.messaging')
security_logger = logging.getLogger('chat.security')
error_logger = logging.getLogger('chat.app')


def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        
        if form.is_valid():
            try:
                user = form.save(commit=False)
                user.save()
                
                auth_logger.info(
                    f'New user registered successfully | '
                    f'Email: {user.email} | '
                    f'User ID: {user.id} | '
                    f'IP: {request.META.get("REMOTE_ADDR")}'
                )
                
                login(request, user)
                
                auth_logger.info(
                    f'User auto-logged in after registration | '
                    f'User ID: {user.id} | '
                    f'Email: {user.email}'
                )
                
                return redirect('home')
                
            except IntegrityError as e:
                security_logger.warning(
                    f'Registration failed - IntegrityError | '
                    f'Attempted email: {request.POST.get("email", "N/A")} | '
                    f'IP: {request.META.get("REMOTE_ADDR")} | '
                    f'Error: {str(e)}'
                )
                return render(request, 'register.html', {
                    'form': form,
                    'error_message': '⚠️ Възникна грешка при регистрацията. Моля, опитайте отново.'
                })
        else:
            security_logger.warning(
                f'Registration form validation failed | '
                f'Errors: {form.errors.as_json()} | '
                f'IP: {request.META.get("REMOTE_ADDR")}'
            )
            return render(request, 'register.html', {'form': form})
    else:
        form = RegistrationForm()
    
    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        if not email or not password:
            security_logger.warning(
                f'Login attempt with empty credentials | '
                f'Email provided: {bool(email)} | '
                f'Password provided: {bool(password)} | '
                f'IP: {request.META.get("REMOTE_ADDR")}'
            )
            return render(request, 'login.html', {
                'form': LoginForm(),
                'error_message': '❌ Невалиден имейл или парола.'
            })
        
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            login(request, user)
            
            auth_logger.info(
                f'User logged in successfully | '
                f'User ID: {user.id} | '
                f'Email: {user.email} | '
                f'IP: {request.META.get("REMOTE_ADDR")} | '
                f'User-Agent: {request.META.get("HTTP_USER_AGENT", "N/A")[:100]}'
            )
            
            return redirect('home')
        
        security_logger.warning(
            f'Failed login attempt | '
            f'Email: {email} | '
            f'IP: {request.META.get("REMOTE_ADDR")} | '
            f'User-Agent: {request.META.get("HTTP_USER_AGENT", "N/A")[:100]}'
        )
        
        return render(request, 'login.html', {
            'form': LoginForm(),
            'error_message': '❌ Невалиден имейл или парола.'
        })
    
    else:
        form = LoginForm()
        return render(request, 'login.html', {'form': form})


@login_required
def logout_view(request):
    user_id = request.user.id
    user_email = request.user.email
    
    logout(request)
    
    auth_logger.info(
        f'User logged out | '
        f'User ID: {user_id} | '
        f'Email: {user_email} | '
        f'IP: {request.META.get("REMOTE_ADDR")}'
    )
    
    return redirect('login')


def home_view(request):
    return render(request, 'home.html')


@login_required
def chat_list_view(request):
    user = request.user
    chats = ChatModel.objects.filter(Q(user1=user) | Q(user2=user)).order_by('-modified')

    chat_data = []
    for chat in chats:
        other_user = chat.user1 if chat.user2 == user else chat.user2
        last_message = MessageModel.objects.filter(chat=chat).order_by('-created').first()

        chat_data.append({
            'chat': chat,
            'other_user': other_user,
            'last_message': last_message,
            'unread_count': MessageModel.objects.filter(sender=other_user, recipient=user, read=False).count(),
            'last_message_created': last_message.created if last_message else None
        })

    chat_data.sort(key=lambda x: (x['last_message_created'] is not None, x['last_message_created']), reverse=True)

    return render(request, 'chat_list.html', {'chat_data': chat_data})


@login_required
def chat_detail_view(request, chat_id):
    chat = get_object_or_404(ChatModel, id=chat_id)
    user = request.user
    if user != chat.user1 and user != chat.user2:
        security_logger.warning(
            f'Unauthorized chat access attempt | '
            f'User ID: {user.id} | '
            f'Email: {user.email} | '
            f'Attempted Chat ID: {chat_id} | '
            f'IP: {request.META.get("REMOTE_ADDR")}'
        )
        raise PermissionDenied
    
    messages = MessageModel.objects.filter(
        chat=chat
    ).order_by('created')
    
    files = UploadedFile.objects.filter(
        chat=chat
    ).order_by('-upload_date')

    other_user = chat.user2 if chat.user1 == user else chat.user1

    messages.filter(recipient=user, read=False).update(read=True)

    message_logger.info(
        f'User opened chat | '
        f'User ID: {user.id} | '
        f'Chat ID: {chat_id} | '
        f'Chatting with: {other_user.email}'
    )

    return render(request, 'chat_detail.html', {
        'chat': chat,
        'messages': messages,
        'files': files,
        'other_user': other_user,
    })


@login_required
def create_chat(request, user1_id, user2_id):
    User = get_user_model()
    
    try:
        user1 = User.objects.get(pk=user1_id)
        user2 = User.objects.get(pk=user2_id)
    except User.DoesNotExist:
        error_logger.error(
            f'Chat creation failed - User not found | '
            f'Requester: {request.user.id} | '
            f'User1 ID: {user1_id} | '
            f'User2 ID: {user2_id}'
        )
        raise Http404("One or both users do not exist.")
    
    chat = ChatModel.dialog_exists(user1, user2)
    if not chat:
        chat = ChatModel.objects.create(
            user1=user1 if user1.pk < user2.pk else user2,
            user2=user2 if user1.pk < user2.pk else user1
        )
        message_logger.info(
            f'New chat created | '
            f'Chat ID: {chat.id} | '
            f'User1: {user1.email} | '
            f'User2: {user2.email} | '
            f'Created by: {request.user.email}'
        )
    
    return redirect('chat_detail', chat_id=chat.id)


@login_required
@require_POST
def async_message_send_view(request, chat_id):
    chat = get_object_or_404(ChatModel, id=chat_id)
    user = request.user

    if user != chat.user1 and user != chat.user2:
        security_logger.warning(
            f'Unauthorized message send attempt | '
            f'User ID: {user.id} | '
            f'Email: {user.email} | '
            f'Chat ID: {chat_id} | '
            f'IP: {request.META.get("REMOTE_ADDR")}'
        )
        return JsonResponse({'error': 'Permission denied'}, status=403)

    data = json.loads(request.body)
    message_text = data.get('message', '')
    recipient = chat.user2 if chat.user1 == user else chat.user1

    if message_text:
        message = MessageModel.objects.create(
            sender=user,
            recipient=recipient,
            text=message_text,
            chat=chat
        )
        
        message_logger.info(
            f'Message sent | '
            f'Message ID: {message.id} | '
            f'Sender: {user.email} (ID: {user.id}) | '
            f'Recipient: {recipient.email} (ID: {recipient.id}) | '
            f'Chat ID: {chat_id} | '
            f'Message length: {len(message_text)} chars'
        )
        
        return JsonResponse({
            'message': message.text, 
            'sender': message.sender.id, 
            'recipient': message.recipient.id, 
            'timestamp': message.created
        })
    else:
        security_logger.warning(
            f'Empty message send attempt | '
            f'User ID: {user.id} | '
            f'Chat ID: {chat_id}'
        )
        return JsonResponse({'error': 'Empty message'}, status=400)


@login_required
@require_POST
def async_file_upload_view(request, chat_id):
    chat = get_object_or_404(ChatModel, id=chat_id)
    user = request.user

    if user != chat.user1 and user != chat.user2:
        security_logger.warning(
            f'Unauthorized file upload attempt | '
            f'User ID: {user.id} | '
            f'Email: {user.email} | '
            f'Chat ID: {chat_id} | '
            f'IP: {request.META.get("REMOTE_ADDR")}'
        )
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if 'file' not in request.FILES:
        file_logger.warning(
            f'File upload attempt with no file | '
            f'User ID: {user.id} | '
            f'Chat ID: {chat_id}'
        )
        return JsonResponse({'error': 'No file provided'}, status=400)

    uploaded_file = request.FILES['file']
    original_filename = uploaded_file.name

    try:
        sanitized_filename, safe_storage_path = validate_uploaded_file(
            uploaded_file, 
            original_filename, 
            user.id
        )
        
        file_instance = UploadedFile.objects.create(
            uploaded_by=user,
            file=uploaded_file,
            original_filename=sanitized_filename,
            file_size=uploaded_file.size,
            chat=chat
        )
        
        increment_bytes_counter(user.id, uploaded_file.size)

        file_logger.info(
            f'File uploaded successfully | '
            f'File ID: {file_instance.id} | '
            f'Original name: {original_filename} | '
            f'Sanitized name: {sanitized_filename} | '
            f'Size: {uploaded_file.size} bytes ({uploaded_file.size / 1024:.2f} KB) | '
            f'User: {user.email} (ID: {user.id}) | '
            f'Chat ID: {chat_id} | '
            f'Storage path: {safe_storage_path}'
        )

        return JsonResponse({
            'success': True,
            'file_id': str(file_instance.id),
            'file_url': file_instance.file.url,
            'file_name': file_instance.original_filename
        })
        
    except ValidationError as e:
        security_logger.warning(
            f'File upload validation failed | '
            f'User ID: {user.id} | '
            f'Email: {user.email} | '
            f'Original filename: {original_filename} | '
            f'File size: {uploaded_file.size} bytes | '
            f'Chat ID: {chat_id} | '
            f'Validation error: {str(e)} | '
            f'IP: {request.META.get("REMOTE_ADDR")}'
        )
        return JsonResponse({'error': str(e)}, status=400)
    
    except Exception as e:
        error_logger.error(
            f'File upload error | '
            f'User ID: {user.id} | '
            f'Original filename: {original_filename} | '
            f'Chat ID: {chat_id} | '
            f'Error: {str(e)} | '
            f'Error type: {type(e).__name__}',
            exc_info=True
        )
        return JsonResponse({'error': 'File upload failed'}, status=500)


@login_required
def download_file(request, file_id):
    uploaded_file = get_object_or_404(UploadedFile, id=file_id)
    
    if request.user != uploaded_file.chat.user1 and request.user != uploaded_file.chat.user2:
        security_logger.warning(
            f'Unauthorized file download attempt | '
            f'User ID: {request.user.id} | '
            f'Email: {request.user.email} | '
            f'File ID: {file_id} | '
            f'File owner: {uploaded_file.uploaded_by.email} | '
            f'IP: {request.META.get("REMOTE_ADDR")}'
        )
        raise PermissionDenied

    if not uploaded_file.file.storage.exists(uploaded_file.file.name):
        error_logger.error(
            f'File not found on disk | '
            f'File ID: {file_id} | '
            f'Expected path: {uploaded_file.file.name} | '
            f'User ID: {request.user.id}'
        )
        return JsonResponse({'error': 'File not found'}, status=404)

    file_content = uploaded_file.file.read()
    
    response = HttpResponse(file_content, content_type='application/octet-stream')
    
    response['Content-Disposition'] = f'attachment; filename="{uploaded_file.original_filename}"'
    
    response['X-Content-Type-Options'] = 'nosniff'
    
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    
    file_logger.info(
        f'File downloaded | '
        f'File ID: {file_id} | '
        f'Filename: {uploaded_file.original_filename} | '
        f'Size: {uploaded_file.file_size} bytes | '
        f'User: {request.user.email} (ID: {request.user.id}) | '
        f'Uploaded by: {uploaded_file.uploaded_by.email} | '
        f'IP: {request.META.get("REMOTE_ADDR")}'
    )
    
    return response


@login_required
def user_list_view(request):
    User = get_user_model()
    users = User.objects.exclude(id=request.user.id)
    return render(request, 'user_list.html', {'users': users})


@login_required
def search_messages(request):
    search_term = request.GET.get('q', '').strip()
    chat_id = request.GET.get('chat_id', '')
    
    if not search_term:
        return JsonResponse({
            'success': False,
            'error': 'Search term is required',
            'count': 0,
            'messages': []
        })
    
    if len(search_term) > 100:
        security_logger.warning(
            f'Search term too long | '
            f'User ID: {request.user.id} | '
            f'Term length: {len(search_term)} | '
            f'IP: {request.META.get("REMOTE_ADDR")}'
        )
        return JsonResponse({
            'success': False,
            'error': 'Search term too long',
            'count': 0,
            'messages': []
        })
    
    try:
        if chat_id:
            chat_id = int(chat_id)
            chat = ChatModel.objects.get(id=chat_id)
            if request.user != chat.user1 and request.user != chat.user2:
                security_logger.warning(
                    f'Unauthorized search attempt | '
                    f'User ID: {request.user.id} | '
                    f'Chat ID: {chat_id} | '
                    f'IP: {request.META.get("REMOTE_ADDR")}'
                )
                return JsonResponse({
                    'success': False,
                    'error': 'Permission denied',
                    'count': 0,
                    'messages': []
                }, status=403)
        
        query = MessageModel.objects.filter(
            text__icontains=search_term
        ).select_related('sender')
        
        if chat_id:
            query = query.filter(chat_id=chat_id)
        
        query = query.filter(
            Q(chat__user1=request.user) | Q(chat__user2=request.user)
        )
        
        messages_qs = query.order_by('-created')[:50]
        
        messages = []
        for message in messages_qs:
            messages.append({
                'id': message.id,
                'text': message.text,
                'created': message.created.isoformat(),
                'sender_name': message.sender.name,
                'sender_email': message.sender.email
            })
        
        message_logger.info(
            f'Search performed | '
            f'User ID: {request.user.id} | '
            f'Search term: "{search_term}" | '
            f'Chat ID: {chat_id if chat_id else "All chats"} | '
            f'Results found: {len(messages)}'
        )
        
        return JsonResponse({
            'success': True,
            'count': len(messages),
            'messages': messages
        })
        
    except ValueError:
        error_logger.error(
            f'Invalid chat ID in search | '
            f'User ID: {request.user.id} | '
            f'Chat ID value: {chat_id}'
        )
        return JsonResponse({
            'success': False,
            'error': 'Invalid chat ID',
            'count': 0,
            'messages': []
        }, status=400)
        
    except ChatModel.DoesNotExist:
        error_logger.error(
            f'Chat not found in search | '
            f'User ID: {request.user.id} | '
            f'Chat ID: {chat_id}'
        )
        return JsonResponse({
            'success': False,
            'error': 'Chat not found',
            'count': 0,
            'messages': []
        }, status=404)
        
    except Exception as e:
        error_logger.error(
            f'Search error | '
            f'User ID: {request.user.id} | '
            f'Search term: "{search_term}" | '
            f'Error: {str(e)}',
            exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': 'Search failed',
            'count': 0,
            'messages': []
        }, status=500)