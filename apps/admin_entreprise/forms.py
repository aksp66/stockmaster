from django import forms
from apps.stock.models import Entrepot

class EntrepotForm(forms.ModelForm):
    class Meta:
        model = Entrepot
        fields = ['nom', 'adresse', 'ville', 'pays', 'telephone', 'responsable']
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2, 'class': 'w-full border rounded px-3 py-2'}),
            'nom': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'ville': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'pays': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'telephone': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'responsable': forms.Select(attrs={'class': 'w-full border rounded px-3 py-2'}),
        }

    def __init__(self, *args, **kwargs):
        # Récupérer l'entreprise (passée en initial ou depuis l'instance)
        entreprise = None
        if 'initial' in kwargs and 'entreprise' in kwargs['initial']:
            entreprise = kwargs['initial']['entreprise']
        if 'instance' in kwargs and kwargs['instance'] and kwargs['instance'].entreprise:
            entreprise = kwargs['instance'].entreprise
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['responsable'].queryset = entreprise.utilisateurs.filter(is_active=True)
        else:
            self.fields['responsable'].queryset = self.fields['responsable'].queryset.none()