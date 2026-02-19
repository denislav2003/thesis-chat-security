import json
import logging
import base64
from channels.consumer import AsyncConsumer
from channels.db import database_sync_to_async
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from chat.models import ChatModel, MessageModel, UploadedFile

User = get_user_model()
logger = logging.getLogger(__name__)


class ChatConsumer(AsyncConsumer):
    async def websocket_connect(self, event):
        user = self.scope['user']
        if not user.is_authenticated:
            logger.warning('Unauthenticated user tried to connect.')
            await self.close()
            return

        logger.info(f'User {user.id} connected')
        self.chat_room = f'user_chatroom_{user.id}'
        
        await self.channel_layer.group_add(
            self.chat_room,
            self.channel_name
        )
        await self.send({
            'type': 'websocket.accept'
        })

    async def websocket_receive(self, event):
        logger.info(f'Received message: {event}')
        try:
            received_data = json.loads(event['text'])
            msg = received_data.get('message')
            sent_by_id = received_data.get('sent_by')
            send_to_id = received_data.get('send_to')
            thread_id = received_data.get('thread_id')
            file_data = received_data.get('file_data', None)
            file_name = received_data.get('file_name', None)
            
            if not msg and not file_data:
                raise ValueError('Empty message or file missing')

            thread, sent_by_user, send_to_user = await self.get_chat_data(thread_id, sent_by_id, send_to_id)
            if not (thread and sent_by_user and send_to_user):
                raise ValueError('Invalid chat data')

            if file_data and file_name:
                file_instance = await self.save_file(file_data, file_name, sent_by_user, thread)
                file_id = file_instance.id
                file_url = file_instance.file.url
                msg = f"{sent_by_user.name} изпрати файл."
            else:
                file_instance = None
                file_id = None

            message = await self.create_chat_message(thread, sent_by_user, send_to_user, msg, file_id)

            response = {
                'type': 'message',
                'message': msg,
                'sent_by': sent_by_user.id,
                'thread_id': thread_id,
                'file': {
                    'file_id': str(file_instance.id),
                    'file_url': file_url,
                    'file_name': file_instance.file.name
                } if file_instance else None
            }

            other_user_chat_room = f'user_chatroom_{send_to_id}'
            await self.send_to_group(other_user_chat_room, response)
            await self.send_to_group(self.chat_room, response)
        except ValueError as e:
            logger.error(f'Error: {str(e)}')
            await self.send({
                'type': 'websocket.send',
                'text': json.dumps({'error': str(e)})
            })
        except Exception as e:
            logger.error(f'Unexpected error: {str(e)}')
            await self.send({
                'type': 'websocket.send',
                'text': json.dumps({'error': 'Unexpected error occurred'})
            })

    async def websocket_disconnect(self, event):
        logger.info(f'User {self.scope["user"].id} disconnected')
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
            logger.error(f'ChatModel with id {thread_id} does not exist')
            return None, None, None
        except User.DoesNotExist as e:
            logger.error(f'User error: {str(e)}')
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
            
            unsafe_filename = file_name
            
            data = ContentFile(decoded_data, name=f'{user.id}/{unsafe_filename}')
            
            return UploadedFile.objects.create(
                uploaded_by=user,
                file=data,
                chat=chat
            )
        except Exception as e:
            logger.error(f'File save error: {str(e)}')
            raise

    async def send_to_group(self, group_name, message):
        await self.channel_layer.group_send(
            group_name,
            {
                'type': 'chat_message',
                'text': json.dumps(message)
            }
        )