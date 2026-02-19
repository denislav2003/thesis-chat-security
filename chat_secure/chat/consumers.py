import json
import base64
from channels.consumer import AsyncConsumer
from channels.db import database_sync_to_async
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from chat.models import ChatModel, MessageModel, UploadedFile
from chat.utils import (
    validate_uploaded_file,
    increment_bytes_counter,
)
import logging

User = get_user_model()

file_logger = logging.getLogger('chat.files')
message_logger = logging.getLogger('chat.messaging')
security_logger = logging.getLogger('chat.security')
error_logger = logging.getLogger('chat.app')


class ChatConsumer(AsyncConsumer):
    async def websocket_connect(self, event):
        user = self.scope['user']
        if not user.is_authenticated:
            await self.log_security_warning(
                'Unauthenticated WebSocket connection attempt',
                None
            )
            await self.close()
            return

        self.chat_room = f'user_chatroom_{user.id}'
        
        await self.channel_layer.group_add(
            self.chat_room,
            self.channel_name
        )
        await self.send({
            'type': 'websocket.accept'
        })
        
        await self.log_message_info(
            f'WebSocket connected',
            user.id,
            {'user_email': user.email}
        )

    async def websocket_receive(self, event):
        user = self.scope['user']
        
        try:
            received_data = json.loads(event['text'])
            msg = received_data.get('message')
            sent_by_id = received_data.get('sent_by')
            send_to_id = received_data.get('send_to')
            thread_id = received_data.get('thread_id')
            file_data = received_data.get('file_data', None)
            file_name = received_data.get('file_name', None)
            
            if not msg and not file_data:
                await self.log_security_warning(
                    'Empty WebSocket message received',
                    user.id,
                    {'thread_id': thread_id}
                )
                raise ValueError('Empty message or file missing')

            thread, sent_by_user, send_to_user = await self.get_chat_data(
                thread_id, sent_by_id, send_to_id
            )
            if not (thread and sent_by_user and send_to_user):
                await self.log_error(
                    'Invalid chat data in WebSocket message',
                    user.id,
                    {
                        'thread_id': thread_id,
                        'sent_by_id': sent_by_id,
                        'send_to_id': send_to_id
                    }
                )
                raise ValueError('Invalid chat data')

            if file_data and file_name:
                try:
                    file_instance = await self.save_file(
                        file_data, file_name, sent_by_user, thread
                    )
                    file_id = file_instance.id
                    file_url = file_instance.file.url
                    file_display_name = file_instance.original_filename
                    msg = f"{sent_by_user.name} изпрати файл: {file_display_name}"
                except ValidationError as e:
                    await self.send({
                        'type': 'websocket.send',
                        'text': json.dumps({
                            'type': 'error',
                            'error': str(e)
                        })
                    })
                    return
            else:
                file_instance = None
                file_id = None
                file_display_name = None

            message = await self.create_chat_message(
                thread, sent_by_user, send_to_user, msg, file_id
            )

            await self.log_message_info(
                'WebSocket message processed',
                user.id,
                {
                    'message_id': message.id,
                    'recipient_id': send_to_user.id,
                    'thread_id': thread_id,
                    'has_file': bool(file_instance),
                    'message_length': len(msg) if msg else 0
                }
            )

            response = {
                'type': 'message',
                'message': msg,
                'sent_by': sent_by_user.id,
                'thread_id': thread_id,
                'file': {
                    'file_id': str(file_instance.id),
                    'file_url': file_url,
                    'file_name': file_display_name
                } if file_instance else None
            }

            other_user_chat_room = f'user_chatroom_{send_to_id}'
            await self.send_to_group(other_user_chat_room, response)
            await self.send_to_group(self.chat_room, response)
            
        except ValueError as e:
            await self.log_error(
                f'ValueError in WebSocket receive: {str(e)}',
                user.id if user.is_authenticated else None,
                {}
            )
            await self.send({
                'type': 'websocket.send',
                'text': json.dumps({'type': 'error', 'error': str(e)})
            })
        except Exception as e:
            await self.log_error(
                f'Unexpected error in WebSocket receive: {str(e)}',
                user.id if user.is_authenticated else None,
                {'error_type': type(e).__name__}
            )
            await self.send({
                'type': 'websocket.send',
                'text': json.dumps({'type': 'error', 'error': 'Unexpected error occurred'})
            })

    async def websocket_disconnect(self, event):
        user = self.scope['user']
        if user.is_authenticated:
            await self.log_message_info(
                'WebSocket disconnected',
                user.id,
                {'user_email': user.email}
            )
        
        await self.channel_layer.group_discard(
            self.chat_room,
            self.channel_name
        )

    async def chat_message(self, event):
        await self.send({
            'type': 'websocket.send',
            'text': event['text']
        })

    @database_sync_to_async
    def get_chat_data(self, thread_id, sent_by_id, send_to_id):
        try:
            thread = ChatModel.objects.get(id=thread_id)
            sent_by_user = User.objects.get(id=sent_by_id)
            send_to_user = User.objects.get(id=send_to_id)
            return thread, sent_by_user, send_to_user
        except ChatModel.DoesNotExist:
            error_logger.error(
                f'ChatModel not found in WebSocket | '
                f'Thread ID: {thread_id}'
            )
            return None, None, None
        except User.DoesNotExist as e:
            error_logger.error(
                f'User not found in WebSocket | '
                f'Sent by ID: {sent_by_id} | '
                f'Send to ID: {send_to_id} | '
                f'Error: {str(e)}'
            )
            return None, None, None

    @database_sync_to_async
    def create_chat_message(self, thread, sender, recipient, msg, file_id):
        file = UploadedFile.objects.get(id=file_id) if file_id else None
        return MessageModel.objects.create(
            sender=sender,
            recipient=recipient,
            text=msg,
            file=file,
            chat=thread
        )

    @database_sync_to_async
    def save_file(self, file_data, file_name, user, chat):
        try:
            format, imgstr = file_data.split(';base64,')
            decoded_data = base64.b64decode(imgstr)
            
            from django.core.files.uploadedfile import InMemoryUploadedFile
            from io import BytesIO
            
            file_obj = InMemoryUploadedFile(
                file=BytesIO(decoded_data),
                field_name='file',
                name=file_name,
                content_type=format.split(':')[1] if ':' in format else 'application/octet-stream',
                size=len(decoded_data),
                charset=None
            )
            
            sanitized_filename, safe_storage_path = validate_uploaded_file(
                file_obj,
                file_name,
                user.id
            )
            
            data = ContentFile(decoded_data, name=safe_storage_path)
            
            file_instance = UploadedFile.objects.create(
                uploaded_by=user,
                file=data,
                original_filename=sanitized_filename,
                file_size=len(decoded_data),
                chat=chat
            )
            
            increment_bytes_counter(user.id, len(decoded_data))
            
            file_logger.info(
                f'File uploaded via WebSocket | '
                f'File ID: {file_instance.id} | '
                f'Original name: {file_name} | '
                f'Sanitized name: {sanitized_filename} | '
                f'Size: {len(decoded_data)} bytes ({len(decoded_data) / 1024:.2f} KB) | '
                f'User: {user.email} (ID: {user.id}) | '
                f'Chat ID: {chat.id} | '
                f'Storage path: {safe_storage_path}'
            )
            
            return file_instance
            
        except ValidationError as e:
            security_logger.warning(
                f'WebSocket file upload validation failed | '
                f'User ID: {user.id} | '
                f'Email: {user.email} | '
                f'Original filename: {file_name} | '
                f'File size: {len(decoded_data) if "decoded_data" in locals() else "N/A"} bytes | '
                f'Chat ID: {chat.id} | '
                f'Validation error: {str(e)}'
            )
            raise
        except Exception as e:
            error_logger.error(
                f'WebSocket file upload error | '
                f'User ID: {user.id} | '
                f'Original filename: {file_name} | '
                f'Chat ID: {chat.id} | '
                f'Error: {str(e)} | '
                f'Error type: {type(e).__name__}',
                exc_info=True
            )
            raise ValidationError('File upload failed')

    async def send_to_group(self, group_name, message):
        await self.channel_layer.group_send(
            group_name,
            {
                'type': 'chat_message',
                'text': json.dumps(message)
            }
        )
    
    @database_sync_to_async
    def log_message_info(self, message, user_id, extra_data=None):
        extra_info = f' | {" | ".join(f"{k}: {v}" for k, v in extra_data.items())}' if extra_data else ''
        message_logger.info(
            f'{message} | '
            f'User ID: {user_id if user_id else "N/A"}'
            f'{extra_info}'
        )
    
    @database_sync_to_async
    def log_security_warning(self, message, user_id, extra_data=None):
        extra_info = f' | {" | ".join(f"{k}: {v}" for k, v in extra_data.items())}' if extra_data else ''
        security_logger.warning(
            f'{message} | '
            f'User ID: {user_id if user_id else "N/A"}'
            f'{extra_info}'
        )
    
    @database_sync_to_async
    def log_error(self, message, user_id, extra_data=None):
        extra_info = f' | {" | ".join(f"{k}: {v}" for k, v in extra_data.items())}' if extra_data else ''
        error_logger.error(
            f'{message} | '
            f'User ID: {user_id if user_id else "N/A"}'
            f'{extra_info}'
        )