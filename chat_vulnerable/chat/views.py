from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from .forms import RegistrationForm, LoginForm
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.db import connection
import json
from .models import ChatModel, MessageModel, UploadedFile

User = get_user_model()


def set_vulnerable_session_cookie(request, response):
    if hasattr(request, 'session') and request.session.session_key:
        response.set_cookie(
            key='sessionid',
            value=request.session.session_key,
            max_age=1209600,
            httponly=False,
            secure=False,
            samesite='Lax',
            path='/',
            domain=None,
        )
    return response


def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        
        email = request.POST.get('email', '')
        if email and User.objects.filter(email=email).exists():
            form = RegistrationForm(request.POST)
            return render(request, 'register.html', {
                'form': form,
                'error_message': '⚠️ Този имейл вече е регистриран в системата.'
            })
        
        if form.is_valid():
            user = form.save(commit=False)
            user.save()
            
            login(request, user, backend='chat.backends.VulnerableAuthBackend')
            
            request.session['_auth_user_id'] = str(user.id)
            request.session.modified = True
            request.session.save()
            
            response = redirect('home')
            response = set_vulnerable_session_cookie(request, response)
            return response
        else:
            return render(request, 'register.html', {'form': form})
    else:
        form = RegistrationForm()
    
    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        error_message = None
        
        if not email:
            error_message = '❌ Моля, въведете имейл!'
        elif not password:
            error_message = '❌ Моля, въведете парола!'
        else:
            user = authenticate(request, username=email, password=password)
            
            if user is not None:
                if user.is_active:
                    login(request, user, backend='chat.backends.VulnerableAuthBackend')
                    
                    request.session['_auth_user_id'] = str(user.id)
                    request.session['_auth_user_backend'] = 'chat.backends.VulnerableAuthBackend'
                    request.session.modified = True
                    request.session.save()
                    
                    response = redirect('home')
                    
                    response.set_cookie(
                        key='sessionid',
                        value=request.session.session_key,
                        max_age=1209600,
                        httponly=False,
                        secure=False,
                        samesite='Lax',
                        path='/',
                    )
                    
                    return response
                else:
                    error_message = '❌ Този акаунт е неактивен.'
            else:
                try:
                    User.objects.get(email=email)
                    error_message = '❌ Грешна парола! (Имейлът е валиден)'
                except User.DoesNotExist:
                    error_message = '❌ Потребител с този имейл не съществува!'
        
        form = LoginForm()
        return render(request, 'login.html', {
            'form': form,
            'error_message': error_message
        })
    
    else:
        form = LoginForm()
        return render(request, 'login.html', {'form': form})
    

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


def home_view(request):
    response = render(request, 'home.html')
    
    if request.user.is_authenticated:
        response = set_vulnerable_session_cookie(request, response)
    
    return response


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

    response = render(request, 'chat_list.html', {'chat_data': chat_data})
    
    response = set_vulnerable_session_cookie(request, response)
    
    return response


@login_required
def chat_detail_view(request, chat_id):
    chat = get_object_or_404(ChatModel, id=chat_id)
    user = request.user
    if user != chat.user1 and user != chat.user2:
        raise PermissionDenied
    
    messages = MessageModel.objects.filter(
        chat=chat
    ).order_by('created')
    
    files = UploadedFile.objects.filter(
        chat=chat
    ).order_by('-upload_date')

    other_user = chat.user2 if chat.user1 == user else chat.user1

    messages.filter(recipient=user, read=False).update(read=True)

    response = render(request, 'chat_detail.html', {
        'chat': chat,
        'messages': messages,
        'files': files,
        'other_user': other_user,
    })
    
    response = set_vulnerable_session_cookie(request, response)
    
    return response


@login_required
def create_chat(request, user1_id, user2_id):
    User = get_user_model()
    
    try:
        user1 = User.objects.get(pk=user1_id)
        user2 = User.objects.get(pk=user2_id)
    except User.DoesNotExist:
        raise Http404("One or both users do not exist.")
    
    chat = ChatModel.dialog_exists(user1, user2)
    if not chat:
        chat = ChatModel.objects.create(
            user1=user1 if user1.pk < user2.pk else user2,
            user2=user2 if user1.pk < user2.pk else user1
        )
    
    return redirect('chat_detail', chat_id=chat.id)


@login_required
@require_POST
def async_message_send_view(request, chat_id):
    chat = get_object_or_404(ChatModel, id=chat_id)
    user = request.user

    if user != chat.user1 and user != chat.user2:
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
        return JsonResponse({
            'message': message.text, 
            'sender': message.sender.id, 
            'recipient': message.recipient.id, 
            'timestamp': message.created
        })
    else:
        return JsonResponse({'error': 'Empty message'}, status=400)
    

@login_required
@require_POST
def async_file_upload_view(request, chat_id):
    chat = get_object_or_404(ChatModel, id=chat_id)
    user = request.user

    if user != chat.user1 and user != chat.user2:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file provided'}, status=400)

    uploaded_file = request.FILES['file']
    
    original_filename = uploaded_file.name
    
    file_instance = UploadedFile.objects.create(
        uploaded_by=user,
        file=uploaded_file,
        chat=chat
    )

    return JsonResponse({
        'file_url': file_instance.file.url,
        'file_name': file_instance.file.name
    })


@login_required
def download_file(request, file_id):
    uploaded_file = get_object_or_404(UploadedFile, id=file_id)
    
    if request.user != uploaded_file.chat.user1 and request.user != uploaded_file.chat.user2:
        raise PermissionDenied

    if not uploaded_file.file.storage.exists(uploaded_file.file.name):
        return JsonResponse({'error': 'File not found'}, status=404)

    response = HttpResponse(uploaded_file.file, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{uploaded_file.file.name}"'
    return response


@login_required
def user_list_view(request):
    User = get_user_model()
    users = User.objects.exclude(id=request.user.id)
    
    response = render(request, 'user_list.html', {'users': users})
    
    response = set_vulnerable_session_cookie(request, response)
    
    return response


@login_required
def search_messages(request):
    search_term = request.GET.get('q', '')
    chat_id = request.GET.get('chat_id', '')
    
    from django.db import connection
    cursor = connection.cursor()
    
    query = f"""
        SELECT 
            m.id,
            m.text,
            m.created,
            u.name as sender_name,
            u.email as sender_email
        FROM chat_messagemodel m
        JOIN chat_user u ON m.sender_id = u.id
        WHERE m.text LIKE '%{search_term}%'
    """
    
    try:
        cursor.execute(query)
        results = cursor.fetchall()
        
        messages = []
        for row in results:
            messages.append({
                'id': row[0],
                'text': row[1] if len(row) > 1 else '',
                'created': str(row[2]) if len(row) > 2 else '',
                'sender_name': row[3] if len(row) > 3 else '',
                'sender_email': row[4] if len(row) > 4 else ''
            })
        
        return JsonResponse({
            'success': True,
            'count': len(messages),
            'messages': messages
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }, status=500)