from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id': 'password',
            'required': True,
            'autocomplete': 'new-password'
        }),
        label='',
        required=True,
        help_text='Минимум 8 символа. Трябва да съдържа букви, цифри и символи и да не е често срещана парола.',
        error_messages={
            'required': 'Паролата е задължителна.'
        }
    )
    
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id': 'confirm_password',
            'required': True,
            'autocomplete': 'new-password'
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
                'required': True,
                'autocomplete': 'email'
            }),
            'name': forms.TextInput(attrs={
                'id': 'name',
                'required': True,
                'autocomplete': 'name'
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
                'unique': 'Възникна грешка при регистрацията.'
            },
            'name': {
                'required': 'Името е задължително.',
            }
        }
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        
        if password:
            try:
                validate_password(password)
            except ValidationError as e:
                error_messages = []
                for error in e.messages:
                    if 'at least 8 characters' in error:
                        error_messages.append('Паролата трябва да съдържа поне 8 символа.')
                    elif 'too common' in error:
                        error_messages.append('Тази парола е твърде често срещана.')
                    elif 'entirely numeric' in error:
                        error_messages.append('Паролата не може да съдържа само цифри.')
                    elif 'too similar' in error:
                        error_messages.append('Паролата е твърде подобна на личната ви информация.')
                    else:
                        error_messages.append(error)
                
                raise forms.ValidationError(error_messages)
        
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        
        if password and password_confirm:
            if password != password_confirm:
                raise forms.ValidationError('Паролите не съвпадат.')
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    error_messages = {
        'invalid_login': 'Невалидни credentials. Моля, опитайте отново.',
        'inactive': 'Този акаунт е неактивен.',
    }
    
    username = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'id': 'username',
            'required': True,
            'autocomplete': 'email'
        }),
        label='',
        error_messages={
            'required': 'Имейлът е задължителен.',
            'invalid': 'Моля, въведете валиден имейл адрес.',
        }
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id': 'password',
            'required': True,
            'autocomplete': 'current-password'
        }),
        label='',
        error_messages={
            'required': 'Паролата е задължителна.',
        }
    )