import os
import re
import mimetypes
from django.core.exceptions import ValidationError
from django.core.cache import cache
from datetime import datetime, timedelta


ALLOWED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp',
    '.pdf', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.rar',
}

ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp',
    'application/pdf',
    'text/plain',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/zip',
    'application/x-rar-compressed',
}

FILE_SIGNATURES = {
    'jpg': [b'\xFF\xD8\xFF'],
    'png': [b'\x89PNG\r\n\x1a\n'],
    'gif': [b'GIF87a', b'GIF89a'],
    'pdf': [b'%PDF'],
    'zip': [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'],
}

BLOCKED_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.com', '.pif', '.scr',
    '.sh', '.bash', '.csh', '.ksh',
    '.php', '.php3', '.php4', '.php5', '.phtml',
    '.jsp', '.asp', '.aspx',
    '.js', '.vbs', '.vbe',
    '.html', '.htm', '.svg',
    '.jar', '.war',
    '.py', '.pyc', '.pyw',
    '.rb', '.pl', '.cgi',
}


def validate_file_extension(filename):
    if not filename:
        raise ValidationError('Filename cannot be empty')
    
    ext = os.path.splitext(filename)[1].lower()
    
    if not ext:
        raise ValidationError('Файлът трябва да има разширение (extension)')
    
    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError(
            f'Файлов тип "{ext}" не е позволен от съображения за сигурност'
        )
    
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f'Файлов тип "{ext}" не е позволен. '
            f'Разрешени типове: {", ".join(sorted(ALLOWED_EXTENSIONS))}'
        )
    
    return ext


def validate_mime_type(file_obj, filename):
    mime_type = None
    
    guessed_type, _ = mimetypes.guess_type(filename)
    
    file_obj.seek(0)
    file_start = file_obj.read(512)
    file_obj.seek(0)
    
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    
    if ext in FILE_SIGNATURES:
        valid_signature = False
        for signature in FILE_SIGNATURES[ext]:
            if file_start.startswith(signature):
                valid_signature = True
                break
        
        if not valid_signature:
            raise ValidationError(
                'Съдържанието на файла не съответства на декларираното разширение. '
                'Възможна е подмяна на файлов тип.'
            )
    
    if guessed_type and guessed_type not in ALLOWED_MIME_TYPES:
        raise ValidationError(
            f'MIME type "{guessed_type}" не е позволен'
        )


def validate_file_size(file_obj, max_size_mb=10):
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if file_obj.size > max_size_bytes:
        raise ValidationError(
            f'Файлът е твърде голям. '
            f'Максимален размер: {max_size_mb}MB. '
            f'Вашият файл: {file_obj.size / (1024 * 1024):.2f}MB'
        )


def sanitize_filename(filename, max_length=100):
    if not filename:
        return 'unnamed'
    
    filename = os.path.basename(filename)
    
    filename = filename.replace('\x00', '')
    
    name, ext = os.path.splitext(filename)
    
    name = re.sub(r'[^\w\s\-.]', '', name)
    
    name = re.sub(r'\.+', '.', name)
    
    name = name.strip('. ')
    
    if len(name) > max_length:
        name = name[:max_length]
    
    if not name:
        name = 'file'
    
    ext = ext.lower()
    
    return f"{name}{ext}"


def generate_safe_filename(original_filename, user_id):
    import uuid
    from datetime import datetime
    
    ext = os.path.splitext(original_filename)[1].lower()
    
    unique_id = uuid.uuid4().hex
    
    now = datetime.now()
    year = now.strftime('%Y')
    month = now.strftime('%m')
    
    safe_path = f'uploads/{user_id}/{year}/{month}/{unique_id}{ext}'
    
    return safe_path


def check_upload_rate_limit(user_id, max_files_per_minute=10, max_mb_per_hour=100):
    files_key = f'upload_rate_files_{user_id}'
    bytes_key = f'upload_rate_bytes_{user_id}'
    
    files_count = cache.get(files_key, 0)
    if files_count >= max_files_per_minute:
        raise ValidationError(
            f'Превишили сте лимита за upload-ване на файлове. '
            f'Максимум: {max_files_per_minute} файла на минута. '
            f'Моля, изчакайте малко преди да опитате отново.'
        )
    
    cache.set(files_key, files_count + 1, 60)
    
    bytes_count = cache.get(bytes_key, 0)
    max_bytes = max_mb_per_hour * 1024 * 1024
    
    if bytes_count >= max_bytes:
        raise ValidationError(
            f'Превишили сте лимита за общ размер на upload-вани файлове. '
            f'Максимум: {max_mb_per_hour}MB на час. '
            f'Моля, изчакайте преди да upload-вате повече файлове.'
        )


def increment_bytes_counter(user_id, file_size):
    bytes_key = f'upload_rate_bytes_{user_id}'
    bytes_count = cache.get(bytes_key, 0)
    cache.set(bytes_key, bytes_count + file_size, 3600)


def validate_uploaded_file(file_obj, filename, user_id):
    check_upload_rate_limit(user_id)
    
    validate_file_size(file_obj, max_size_mb=10)
    
    ext = validate_file_extension(filename)
    
    validate_mime_type(file_obj, filename)
    
    sanitized_filename = sanitize_filename(filename)
    
    safe_storage_path = generate_safe_filename(filename, user_id)
    
    return sanitized_filename, safe_storage_path