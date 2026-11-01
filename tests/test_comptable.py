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


class MargesAuCoutReelTests(EntrepriseTestCase):

    def test_marge_au_cout_du_moment_de_la_vente(self):
        p = creer_produit(self.ent, nom="Huile", prix="100")
        p.prix_vente = Decimal('250')
        p.save()
        for type_m, q, prix, jours, dest in [(TypeMouvement.ENTREE, 10, '100', 40, True),
                                             (TypeMouvement.SORTIE, 5, None, 30, False),
                                             (TypeMouvement.ENTREE, 5, '300', 20, True)]:
            m = Mouvement.objects.create(type_mouvement=type_m, produit=p, quantite=q,
                                         prix_unitaire_snapshot=Decimal(prix) if prix else None,
                                         entrepot_destination=self.entrepot if dest else None,
                                         entrepot_source=None if dest else self.entrepot,
                                         date_mouvement=timezone.now() - timedelta(days=jours))
            _appliquer_mouvement(m)
        self.connecter('comptable')
        ligne = next(m for m in self.client.get(reverse('comptable:marges')).context['marges'] if m['nom'] == 'Huile')
        # Les 5 ventes ont eu lieu quand le coût moyen était de 100 (il vaut 200 aujourd'hui)
        self.assertEqual((ligne['prix_achat_cump'], ligne['marge_totale']), (Decimal(100), Decimal(750)))
        self.assertEqual(ligne['marge_pct'], Decimal(60))


class AnciennesPredictionsTests(EntrepriseTestCase):

    def test_migration_vers_la_convention_actuelle(self):
        import importlib
        from django.apps import apps as django_apps
        from apps.stock.models import PredictionStock
        migration = importlib.import_module('apps.stock.migrations.0007_predictions_ancienne_convention')
        cible = timezone.localdate() + timedelta(days=30)
        ancienne = PredictionStock.objects.create(produit=self.produit, date_cible=cible, quantite_prevue=600,
                                                  borne_inferieure=12, borne_superieure=31, confiance=80,
                                                  quantite_recommandee_commande=40, modele_utilise='prophet')
        actuelle = PredictionStock.objects.create(produit=self.produit, date_cible=cible + timedelta(days=1),
                                                  quantite_prevue=600, borne_inferieure=450, borne_superieure=750,
                                                  confiance=0.9, modele_utilise='prophet')
        migration.vers_convention_actuelle(django_apps, None)
        ancienne.refresh_from_db()
        actuelle.refresh_from_db()
        self.assertEqual((ancienne.borne_inferieure, ancienne.borne_superieure, ancienne.quantite_recommandee_commande,
                          ancienne.quantite_prevue), (None, None, None, 600))
        self.assertEqual((actuelle.borne_superieure, actuelle.confiance), (750, 90))

    def test_nettoyage_garde_la_plus_recente_par_produit(self):
        from io import StringIO
        from django.core.management import call_command
        from apps.stock.models import PredictionStock
        for i in range(3):
            PredictionStock.objects.create(produit=self.produit, date_cible=timezone.localdate() + timedelta(days=28 + i),
                                           quantite_prevue=60, modele_utilise='prophet')
        recente = PredictionStock.objects.order_by('-created_at', '-date_cible').first()
        call_command('nettoyer_predictions', '--apercu', stdout=StringIO())
        self.assertEqual(PredictionStock.objects.count(), 3)  # l'aperçu ne supprime rien
        call_command('nettoyer_predictions', stdout=StringIO())
        self.assertEqual(list(PredictionStock.objects.all()), [recente])


    def test_tache_hebdomadaire_conserve_l_historique_recent(self):
        from apps.ia.tasks import nettoyer_predictions
        from apps.stock.models import PredictionStock
        anciennes = [PredictionStock.objects.create(produit=self.produit, quantite_prevue=60, modele_utilise='prophet',
                                                    date_cible=timezone.localdate() + timedelta(days=i))
                     for i in range(3)]
        PredictionStock.objects.filter(pk=anciennes[0].pk).update(created_at=timezone.now() - timedelta(days=120))
        PredictionStock.objects.filter(pk=anciennes[1].pk).update(created_at=timezone.now() - timedelta(days=10))
        self.assertEqual(nettoyer_predictions(), {'supprimees': 1})  # seule celle de plus de 90 jours
        self.assertEqual(set(PredictionStock.objects.values_list('pk', flat=True)), {anciennes[1].pk, anciennes[2].pk})


class PrixDeVentePratiqueTests(EntrepriseTestCase):
    """Le chiffre d'affaires utilise le prix enregistré sur chaque vente, pas le prix de vente actuel."""

    def setUp(self):
        self.produit.prix_vente = Decimal('1500')
        self.produit.save()

    def _mvt(self, type_m, quantite, vers_destination, **champs):
        m = Mouvement.objects.create(type_mouvement=type_m, produit=self.produit, quantite=quantite,
                                     prix_unitaire_snapshot=Decimal('1000'),
                                     entrepot_destination=self.entrepot if vers_destination else None,
                                     entrepot_source=None if vers_destination else self.entrepot, **champs)
        _appliquer_mouvement(m)
        return m

    def test_prix_enregistre_sur_les_ventes_et_retours_clients(self):
        vente = self._mvt(TypeMouvement.SORTIE, 2, False)
        retour_client = self._mvt(TypeMouvement.RETOUR, 1, True)
        retour_fournisseur = self._mvt(TypeMouvement.RETOUR, 1, False)
        perte = self._mvt(TypeMouvement.PERTE, 1, False)
        self.assertEqual((vente.prix_vente_snapshot, retour_client.prix_vente_snapshot), (1500, 1500))
        self.assertEqual((retour_fournisseur.prix_vente_snapshot, perte.prix_vente_snapshot), (None, None))

    def test_changement_de_prix_sans_effet_sur_les_ventes_passees(self):
        self._mvt(TypeMouvement.SORTIE, 2, False)                     # 2 × 1 500
        self.produit.prix_vente = Decimal('2000')
        self.produit.save()
        self._mvt(TypeMouvement.SORTIE, 1, False)                     # 1 × 2 000
        self._mvt(TypeMouvement.RETOUR, 1, True)                      # retour à 2 000
        self.assertEqual(valoriser_produits([self.produit])[self.produit.pk]['ca'], Decimal(3000))
        self.connecter('comptable')
        self.assertEqual(self.client.get(reverse('comptable:rapports')).context['ca'], Decimal(3000))
        ligne = self.client.get(reverse('comptable:marges')).context['marges'][0]
        # 2 vendus nets pour 3 000 : prix moyen pratiqué 1 500, coût 1 000
        self.assertEqual((ligne['prix_vente'], ligne['prix_vente_actuel'], ligne['marge_totale']),
                         (Decimal(1500), Decimal(2000), Decimal(1000)))

    def test_vente_sans_prix_enregistre_au_prix_actuel(self):
        # Mouvements créés avant l'enregistrement du prix (snapshot vide) : prix de vente actuel
        m = self._mvt(TypeMouvement.SORTIE, 2, False)
        Mouvement.objects.filter(pk=m.pk).update(prix_vente_snapshot=None)
        self.assertEqual(valoriser_produits([self.produit])[self.produit.pk]['ca'], Decimal(3000))

    def test_prix_saisi_dans_le_formulaire(self):
        self.connecter('gestionnaire')
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 2, 'entrepot': self.entrepot.pk,
            'prix_vente_unitaire': '1200',
        })
        self.client.post(reverse('gestionnaire:mouvement_form'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 1, 'entrepot': self.entrepot.pk,
            'prix_vente_unitaire': '',
        })
        self.assertEqual(sorted(Mouvement.objects.values_list('prix_vente_snapshot', flat=True)), [1200, 1500])
        html = self.client.get(reverse('gestionnaire:mouvement_form'), {'produit': self.produit.pk}).content.decode()
        self.assertIn('value="1500.00"', html)

    def test_migration_renseigne_les_ventes_existantes(self):
        import importlib
        from django.apps import apps as django_apps
        migration = importlib.import_module('apps.stock.migrations.0008_mouvement_prix_vente_snapshot')
        vente = self._mvt(TypeMouvement.SORTIE, 2, False)
        perte = self._mvt(TypeMouvement.PERTE, 1, False)
        Mouvement.objects.update(prix_vente_snapshot=None)
        migration.renseigner_prix_existants(django_apps, None)
        vente.refresh_from_db()
        perte.refresh_from_db()
        self.assertEqual((vente.prix_vente_snapshot, perte.prix_vente_snapshot), (1500, None))
