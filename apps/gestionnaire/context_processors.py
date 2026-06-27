from apps.stock.models import Alerte

def alertes_count(request):
    if request.user.is_authenticated and hasattr(request.user, 'entreprise'):
        count = Alerte.objects.filter(produit__entreprise=request.user.entreprise, lue=False).count()
        return {'nb_alertes_actives': count}
    return {'nb_alertes_actives': 0}