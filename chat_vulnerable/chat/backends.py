from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.db import connection
import hashlib

User = get_user_model()


class VulnerableAuthBackend(BaseBackend):
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        
        try:
            password_hash = hashlib.md5(password.encode()).hexdigest()
            
            query = f"""
                SELECT id, email, name, password, is_active, is_staff, is_superuser
                FROM chat_user
                WHERE email = '{username}' AND password = '{password_hash}'
            """
            
            with connection.cursor() as cursor:
                cursor.execute(query)
                row = cursor.fetchone()
                
                if row:
                    user = User(
                        id=row[0],
                        email=row[1],
                        name=row[2],
                        password=row[3],
                        is_active=row[4],
                        is_staff=row[5],
                        is_superuser=row[6]
                    )
                    return user
            
        except Exception as e:
            print(f"Authentication error: {e}")
            return None
        
        return None
    
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class VulnerableAuthBackendWithoutPassword(BaseBackend):
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            return None
        
        try:
            query = f"""
                SELECT id, email, name, password, is_active, is_staff, is_superuser
                FROM chat_user
                WHERE email = '{username}'
            """
            
            with connection.cursor() as cursor:
                cursor.execute(query)
                row = cursor.fetchone()
                
                if row:
                    user = User(
                        id=row[0],
                        email=row[1],
                        name=row[2],
                        password=row[3],
                        is_active=row[4],
                        is_staff=row[5],
                        is_superuser=row[6]
                    )
                    return user
            
        except Exception as e:
            print(f"Authentication error: {e}")
            return None
        
        return None