from apps.stock.models import Alerte, BonCommande

def alertes_count(request):
    if request.user.is_authenticated and hasattr(request.user, 'entreprise'):
        count = Alerte.objects.filter(produit__entreprise=request.user.entreprise, lue=False).count()
        contexte = {'nb_alertes_actives': count}
        # Badge « commandes en attente » de la barre latérale de l'espace achats
        if request.path.startswith('/responsable-achat/'):
            contexte['nb_bc_en_attente'] = BonCommande.objects.filter(
                entreprise=request.user.entreprise, statut__in=['envoye', 'recu_partiel']
            ).count()
        return contexte
    return {'nb_alertes_actives': 0}
