from django import forms
from apps.entreprises.models import Entreprise, TypeEntreprise
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class Step1TypeEntrepriseForm(forms.Form):
    type_entreprise = forms.ChoiceField(
        choices=TypeEntreprise.choices,
        widget=forms.HiddenInput()  # géré par les cards JS
    )

class Step2EntrepriseForm(forms.ModelForm):
    class Meta:
        model = Entreprise
        fields = ['nom', 'pays', 'ville', 'taille', 'nb_entrepots']
        widgets = {
            'nom':         forms.TextInput(attrs={'placeholder': 'Ex : Entrepôts Koffi SA'}),
            'pays':        forms.TextInput(attrs={'placeholder': 'Togo'}),
            'ville':       forms.TextInput(attrs={'placeholder': 'Lomé'}),
            'taille':      forms.TextInput(attrs={'placeholder': '10-50'}),
            'nb_entrepots':forms.NumberInput(attrs={'min': 1, 'max': 50}),
        }

class Step3AdminForm(forms.Form):
    first_name = forms.CharField(label='Prénom', max_length=100)
    last_name  = forms.CharField(label='Nom', max_length=100)
    email      = forms.EmailField(label='Email professionnel')
    password1  = forms.CharField(label='Mot de passe', widget=forms.PasswordInput(), min_length=8)
    password2  = forms.CharField(label='Confirmer', widget=forms.PasswordInput())

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Un compte avec cet email existe déjà. Veuillez vous connecter ou utiliser une autre adresse.")
        return email

    def clean(self):
        cd = super().clean()
        if cd.get('password1') != cd.get('password2'):
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return cd



class ConnexionForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={'class': '...'}))
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput(attrs={'class': '...'}))