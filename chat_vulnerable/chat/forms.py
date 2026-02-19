from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

User = get_user_model()


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id': 'password',
            'required': True
        }),
        label='',
        required=True,
        error_messages={
            'required': 'Паролата е задължителна.'
        }
    )
    
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id': 'confirm_password',
            'required': True
        }),
        label='',
        required=True,
        error_messages={
            'required': 'Моля, потвърдете паролата.'
        }
    )
    
    class Meta:
        model = User
        fields = ['email', 'name']
        widgets = {
            'email': forms.EmailInput(attrs={
                'id': 'email',
                'required': True
            }),
            'name': forms.TextInput(attrs={
                'id': 'name',
                'required': True
            }),
        }
        labels = {
            'email': '',
            'name': '',
        }
        error_messages = {
            'email': {
                'required': 'Имейлът е задължителен.',
                'invalid': 'Моля, въведете валиден имейл адрес.',
            },
            'name': {
                'required': 'Името е задължително.',
            }
        }
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError('Имейлът е задължителен.')
        return email
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        
        if password and password_confirm:
            if password != password_confirm:
                raise forms.ValidationError('❌ Паролите не съвпадат!')
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    error_messages = {
        'invalid_login': '',
        'inactive': 'Този акаунт е неактивен.',
    }
    
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'id': 'username',
            'required': True
        }),
        label='',
        error_messages={
            'required': 'Имейлът е задължителен.',
        }
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id': 'password',
            'required': True
        }),
        label='',
        error_messages={
            'required': 'Паролата е задължителна.',
        }
    )