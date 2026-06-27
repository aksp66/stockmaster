from django import forms
from apps.stock.models import Produit, Categorie, Mouvement, TypeMouvement, Entrepot, Fournisseur

class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = ['nom', 'description', 'sku', 'code_barres', 'categorie', 'unite_mesure',
                  'seuil_alerte', 'prix_unitaire', 'image', 'fournisseur_principal']

    def __init__(self, *args, **kwargs):
        entreprise = kwargs.pop('entreprise', None)
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['categorie'].queryset = Categorie.objects.filter(entreprise=entreprise)
            self.fields['fournisseur_principal'].queryset = Fournisseur.objects.filter(entreprise=entreprise)


class MouvementForm(forms.ModelForm):
    class Meta:
        model = Mouvement
        fields = ['type_mouvement', 'produit', 'quantite', 'entrepot_source',
                  'entrepot_destination', 'emplacement_source', 'emplacement_destination',
                  'reference', 'note', 'lot_numero', 'date_expiration']

    def __init__(self, *args, **kwargs):
        entreprise = kwargs.pop('entreprise', None)
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['produit'].queryset = Produit.objects.filter(entreprise=entreprise)
            self.fields['entrepot_source'].queryset = Entrepot.objects.filter(entreprise=entreprise)
            self.fields['entrepot_destination'].queryset = Entrepot.objects.filter(entreprise=entreprise)

    def clean(self):
        data = super().clean()
        type_mvt = data.get('type_mouvement')
        entrepot_source = data.get('entrepot_source')
        entrepot_dest = data.get('entrepot_destination')
        if type_mvt == TypeMouvement.TRANSFERT and (not entrepot_source or not entrepot_dest):
            raise forms.ValidationError("Un transfert nécessite un entrepôt source et destination.")
        if type_mvt in (TypeMouvement.SORTIE, TypeMouvement.PERTE) and not entrepot_source:
            raise forms.ValidationError("Une sortie nécessite un entrepôt source.")
        if type_mvt == TypeMouvement.ENTREE and not entrepot_dest:
            raise forms.ValidationError("Une entrée nécessite un entrepôt destination.")
        return data


class InventaireLigneForm(forms.Form):
    """Formulaire simple pour saisir la quantité comptée lors d'un inventaire."""
    quantite_comptee = forms.DecimalField(
        required=False,
        label="Quantité comptée",
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'})
    )