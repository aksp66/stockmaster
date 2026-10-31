"""Valorisation en inventaire permanent (CUMP / FIFO) et rapport périodique du comptable."""
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.comptable.valorisation import FLUX, cump_permanent, prix_fifo, valoriser_produits
from apps.comptable.views import _stocks_dict
from apps.gestionnaire.views import _appliquer_mouvement
from apps.stock.models import Mouvement, Stock, TypeMouvement

from .base import EntrepriseTestCase, creer_produit


class ValorisationTests(EntrepriseTestCase):
    """Produit vierge (sans stock initial) pour maîtriser tout l'historique."""

    def setUp(self):
        self.p = creer_produit(self.ent, nom="Ciment", prix="1000")
        self.p.prix_vente = Decimal('1500')
        self.p.save()

    def _mvt(self, type_m, quantite, jours, prix=None, vers_destination=True):
        m = Mouvement.objects.create(
            type_mouvement=type_m, produit=self.p, quantite=quantite, prix_unitaire_snapshot=prix,
            entrepot_destination=self.entrepot if vers_destination else None,
            entrepot_source=None if vers_destination else self.entrepot,
            date_mouvement=timezone.now() - timedelta(days=jours),
        )
        _appliquer_mouvement(m)

    def _historique(self):
        self._mvt(TypeMouvement.ENTREE, 10, 40, prix=Decimal('100'))                 # 10 @ 100
        self._mvt(TypeMouvement.ENTREE, 10, 20, prix=Decimal('200'))                 # CUMP 150
        self._mvt(TypeMouvement.SORTIE, 5, 10, vers_destination=False)               # vente : 5 × 150
        self._mvt(TypeMouvement.PERTE, 1, 9, vers_destination=False)                 # perte : 150
        self._mvt(TypeMouvement.RETOUR, 2, 8, vers_destination=True)                 # retour client : 2 × 150
        self._mvt(TypeMouvement.RETOUR, 3, 7, vers_destination=False)                # retour fournisseur : 3 × 150
        self._mvt(TypeMouvement.AJUSTEMENT, 1, 6, vers_destination=False)            # manque : 150

    def test_cump_permanent_et_tous_les_flux(self):
        self._historique()
        v = valoriser_produits([self.p], timezone.localdate() - timedelta(days=30), timezone.localdate())[self.p.pk]
        self.assertEqual((v['qte_debut'], v['valeur_debut']), (10, Decimal(1000)))
        self.assertEqual(v['entrees'], Decimal(2000))
        self.assertEqual((v['sorties'], v['pertes'], v['retours_clients'], v['retours_fournisseurs'],
                          v['ajustements_moins']), (Decimal(750), Decimal(150), Decimal(300), Decimal(450), Decimal(150)))
        self.assertEqual((v['qte_fin'], v['valeur_fin'], v['cump']), (12, Decimal(1800), Decimal(150)))
        self.assertEqual(v['ca'], Decimal(4500))  # (5 vendus − 2 retournés) × 1 500
        # Réconciliation : début + entrées − sorties = fin
        flux = sum(v[c] * sens for c, sens in FLUX.items())
        self.assertEqual(v['valeur_debut'] + flux, v['valeur_fin'])
        self.assertEqual(cump_permanent(self.p), Decimal(150))

    def test_periode_passee_valorisee_a_sa_date(self):
        self._historique()
        fin = timezone.localdate() - timedelta(days=15)  # après les deux entrées, avant les sorties
        v = valoriser_produits([self.p], fin - timedelta(days=30), fin)[self.p.pk]
        self.assertEqual((v['qte_fin'], v['valeur_fin'], v['sorties']), (20, Decimal(3000), 0))

    def test_fifo_valorise_aux_entrees_recentes(self):
        self._historique()
        # 12 en stock : 10 du dernier lot à 200 + 2 du lot précédent à 100
        self.assertEqual(prix_fifo(self.p) * 12, Decimal(2200))

    def test_stock_sans_historique_traite_comme_ouverture(self):
        autre = creer_produit(self.ent, nom="Sable", prix="50")
        Stock.objects.create(produit=autre, entrepot=self.entrepot, quantite=8)
        v = valoriser_produits([autre])[autre.pk]
        self.assertEqual((v['qte_fin'], v['valeur_fin']), (8, Decimal(400)))

    def test_stocks_sans_emplacement_compris(self):
        # Le stock du produit de base n'a pas d'emplacement : il était exclu auparavant
        self.assertEqual(_stocks_dict(self.ent)[self.produit.pk], 10)


class RapportComptableTests(EntrepriseTestCase):

    def setUp(self):
        self.connecter('comptable')

    def test_rapport_reconcilie_et_exports(self):
        p = self.produit
        p.prix_vente = Decimal('1300')
        p.save()
        for type_m, q, dest in [(TypeMouvement.SORTIE, 2, False), (TypeMouvement.PERTE, 1, False),
                                (TypeMouvement.RETOUR, 1, True), (TypeMouvement.ENTREE, 5, True)]:
            m = Mouvement.objects.create(type_mouvement=type_m, produit=p, quantite=q, prix_unitaire_snapshot=Decimal('1000'),
                                         entrepot_destination=self.entrepot if dest else None,
                                         entrepot_source=None if dest else self.entrepot)
            _appliquer_mouvement(m)
        response = self.client.get(reverse('comptable:rapports'))
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        flux = ctx['flux']
        self.assertEqual((flux['sorties'], flux['pertes'], flux['retours_clients'], flux['entrees']),
                         (Decimal(2000), Decimal(1000), Decimal(1000), Decimal(5000)))
        self.assertEqual(ctx['stock_initial'] + sum(flux[c] * s for c, s in FLUX.items()), ctx['stock_final'])
        self.assertEqual(ctx['stock_final'], Decimal(13000))  # 13 en stock au coût moyen de 1 000
        # (2 vendus − 1 retourné) × 1 300 ; coût net = 2 000 − 1 000
        self.assertEqual((ctx['ca'], ctx['marge_brute']), (Decimal(1300), Decimal(300)))
        self.assertContains(response, 'Pertes / casse')
        csv = self.client.get(reverse('comptable:rapports'), {'export': 'csv'})
        self.assertIn('Retours clients', csv.content.decode('utf-8-sig'))
        pdf = self.client.get(reverse('comptable:rapports'), {'export': 'pdf'})
        self.assertTrue(pdf.content.startswith(b'%PDF'))

    def test_pas_de_chiffre_d_affaires_invente(self):
        Mouvement.objects.create(type_mouvement=TypeMouvement.SORTIE, produit=self.produit, quantite=2,
                                 entrepot_source=self.entrepot)
        ctx = self.client.get(reverse('comptable:rapports')).context
        self.assertEqual((ctx['ca'], ctx['taux_marge'], ctx['nb_produits_sans_pv']), (0, None, 1))


class CacheEtMargesTests(EntrepriseTestCase):

    def _mvt(self, type_m, quantite, vers_destination):
        m = Mouvement.objects.create(type_mouvement=type_m, produit=self.produit, quantite=quantite,
                                     prix_unitaire_snapshot=Decimal('1000'),
                                     entrepot_destination=self.entrepot if vers_destination else None,
                                     entrepot_source=None if vers_destination else self.entrepot)
        _appliquer_mouvement(m)

    def test_cache_invalide_par_un_nouveau_mouvement(self):
        avant = valoriser_produits([self.produit])[self.produit.pk]['qte_fin']
        self.assertEqual(valoriser_produits([self.produit])[self.produit.pk]['qte_fin'], avant)  # servi par le cache
        self._mvt(TypeMouvement.SORTIE, 3, False)
        self.assertEqual(valoriser_produits([self.produit])[self.produit.pk]['qte_fin'], avant - 3)

    def test_cache_invalide_par_un_changement_de_prix(self):
        Stock.objects.filter(produit=self.produit).update(quantite=10)
        avant = valoriser_produits([self.produit])[self.produit.pk]['valeur_fin']
        self.produit.prix_unitaire = Decimal('2000')
        self.produit.save()
        self.assertEqual(valoriser_produits([self.produit])[self.produit.pk]['valeur_fin'], avant * 2)

    def test_marges_nettes_des_retours_clients(self):
        self.produit.prix_vente = Decimal('1500')
        self.produit.save()
        self._mvt(TypeMouvement.SORTIE, 4, False)
        self._mvt(TypeMouvement.RETOUR, 1, True)    # retour client : annule une vente
        self._mvt(TypeMouvement.RETOUR, 2, False)   # retour fournisseur : sans effet sur les ventes
        self.connecter('comptable')
        ligne = self.client.get(reverse('comptable:marges')).context['marges'][0]
        self.assertEqual((ligne['qte_vendue'], ligne['qte_retournee']), (3, 1))
        csv = self.client.get(reverse('comptable:marges'), {'export': 'csv'}).content.decode('utf-8-sig')
        self.assertIn('dont retours clients', csv)

