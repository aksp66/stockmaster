"""Sorties du magasinier (scan, mouvement rapide) et de l'API mobile : prix de vente pratiqué, cohérence du stock."""
import json
from decimal import Decimal

from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken

from apps.stock.models import Mouvement

from .base import EntrepriseTestCase, creer_entrepot, creer_entreprise, creer_produit, quantite_en_stock


class ScanMagasinierTests(EntrepriseTestCase):

    def setUp(self):
        self.produit.prix_vente = Decimal('1500')
        self.produit.code_barres = '6111111111111'
        self.produit.save()
        self.connecter('magasinier')
        self.url = reverse('magasinier:api_scan')

    def _post(self, **donnees):
        return self.client.post(self.url, json.dumps(donnees), content_type='application/json').json()

    def test_requete_de_la_page_de_scan(self):
        # Requête telle qu'envoyée par scan.html (produit_id + type) : refusée auparavant (« Action non reconnue »)
        rep = self._post(produit_id=str(self.produit.pk), type='sortie', quantite=2,
                         entrepot_id=str(self.entrepot.pk), motif='Client comptoir', prix_vente='1200')
        self.assertTrue(rep['success'], rep)
        self.assertEqual((rep['nouveau_stock'], rep['entrepot_nom']), (8, self.entrepot.nom))
        mvt = Mouvement.objects.get()
        self.assertEqual((mvt.prix_vente_snapshot, mvt.note), (1200, 'Client comptoir'))
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 8)

    def test_prix_vide_reprend_le_prix_du_produit(self):
        self._post(produit_id=str(self.produit.pk), type='sortie', quantite=1, entrepot_id=str(self.entrepot.pk),
                   prix_vente='')
        self.assertEqual(Mouvement.objects.get().prix_vente_snapshot, 1500)

    def test_prix_invalide_refuse(self):
        for prix in ('-5', 'abc', 'NaN', 'Infinity'):
            rep = self._post(produit_id=str(self.produit.pk), type='sortie', quantite=1,
                             entrepot_id=str(self.entrepot.pk), prix_vente=prix)
            self.assertFalse(rep['success'], prix)
        self.assertFalse(Mouvement.objects.exists())

    def test_prix_ignore_pour_une_entree(self):
        self._post(produit_id=str(self.produit.pk), type='entree', quantite=1, entrepot_id=str(self.entrepot.pk),
                   prix_vente='1200')
        self.assertIsNone(Mouvement.objects.get().prix_vente_snapshot)

    def test_recherche_par_code_et_prix_pour_pre_remplir(self):
        rep = self.client.get(self.url, {'code': '6111111111111'}).json()
        self.assertEqual(rep['prix_vente'], 1500)
        self.assertTrue(self._post(code='6111111111111', action='sortie', quantite=1,
                                   entrepot_id=str(self.entrepot.pk))['success'])

    def test_identifiants_invalides(self):
        self.assertFalse(self._post(produit_id='pas-un-uuid', type='sortie', quantite=1,
                                    entrepot_id=str(self.entrepot.pk))['success'])
        self.assertFalse(self._post(produit_id=str(self.produit.pk), type='sortie', quantite=1,
                                    entrepot_id='pas-un-uuid')['success'])

    def test_page_de_scan_entrepot_par_defaut(self):
        autre = creer_entrepot(self.ent, nom='Dépôt B')
        session = self.client.session
        session['magasinier_entrepot_defaut'] = str(autre.pk)
        session.save()
        html = self.client.get(reverse('magasinier:scan')).content.decode()
        self.assertRegex(html, rf'value="{autre.pk}"\s+selected')
        self.assertIn('id="r-prix-vente"', html)

    def test_mouvement_rapide_avec_prix(self):
        self.client.post(reverse('magasinier:mouvement_rapide'), {
            'produit': self.produit.pk, 'type_mouvement': 'sortie', 'quantite': 2, 'entrepot': self.entrepot.pk,
            'prix_vente': '1350',
        })
        self.assertEqual(Mouvement.objects.get().prix_vente_snapshot, 1350)
        html = self.client.get(reverse('magasinier:mouvement_rapide'), {'produit': self.produit.pk}).content.decode()
        self.assertIn('value="1500.00"', html)


class ApiMobileTests(EntrepriseTestCase):

    def setUp(self):
        self.produit.prix_vente = Decimal('1500')
        self.produit.save()
        token = RefreshToken.for_user(self.users['magasinier']).access_token
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    def _post(self, url, donnees):
        return self.client.post(url, json.dumps(donnees), content_type='application/json', **self.auth)

    def test_rapide_avec_prix_de_vente(self):
        rep = self._post('/api/v1/mouvements/rapide/', {
            'produit_id': str(self.produit.pk), 'type_mouvement': 'sortie', 'quantite': 2,
            'entrepot_id': str(self.entrepot.pk), 'prix_vente': 1250.5,
        })
        self.assertEqual(rep.status_code, 201, rep.content)
        self.assertEqual(Mouvement.objects.get().prix_vente_snapshot, Decimal('1250.50'))

    def test_rapide_prix_invalide_ou_sans_entrepot(self):
        base = {'produit_id': str(self.produit.pk), 'type_mouvement': 'sortie', 'quantite': 1}
        self.assertEqual(self._post('/api/v1/mouvements/rapide/',
                                    {**base, 'entrepot_id': str(self.entrepot.pk), 'prix_vente': -1}).status_code, 400)
        # Sans entrepôt, le mouvement était enregistré sans aucun effet sur le stock
        self.assertEqual(self._post('/api/v1/mouvements/rapide/', base).status_code, 400)
        self.assertEqual(self._post('/api/v1/mouvements/rapide/',
                                    {**base, 'produit_id': 'x', 'entrepot_id': str(self.entrepot.pk)}).status_code, 400)
        self.assertFalse(Mouvement.objects.exists())

    def test_creation_generique_applique_le_stock(self):
        # Utilisée par la file hors ligne de la PWA : le stock n'était pas mis à jour
        rep = self._post('/api/v1/mouvements/', {
            'produit': str(self.produit.pk), 'type_mouvement': 'sortie', 'quantite': '3',
            'entrepot_source': str(self.entrepot.pk), 'prix_vente_snapshot': '1400',
        })
        self.assertEqual(rep.status_code, 201, rep.content)
        mvt = Mouvement.objects.get()
        self.assertEqual((mvt.prix_vente_snapshot, mvt.utilisateur), (1400, self.users['magasinier']))
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 7)

    def test_creation_generique_prix_par_defaut_et_stock_insuffisant(self):
        self._post('/api/v1/mouvements/', {'produit': str(self.produit.pk), 'type_mouvement': 'sortie',
                                           'quantite': '1', 'entrepot_source': str(self.entrepot.pk)})
        self.assertEqual(Mouvement.objects.get().prix_vente_snapshot, 1500)
        rep = self._post('/api/v1/mouvements/', {'produit': str(self.produit.pk), 'type_mouvement': 'perte',
                                                 'quantite': '50', 'entrepot_source': str(self.entrepot.pk)})
        self.assertEqual(rep.status_code, 400)
        self.assertEqual(Mouvement.objects.count(), 1)

    def test_creation_generique_refuse_une_autre_entreprise(self):
        autre = creer_entreprise('Autre')
        produit_b, entrepot_b = creer_produit(autre, nom='Sucre'), creer_entrepot(autre)
        rep = self._post('/api/v1/mouvements/', {'produit': str(produit_b.pk), 'type_mouvement': 'entree',
                                                 'quantite': '5', 'entrepot_destination': str(entrepot_b.pk)})
        self.assertEqual(rep.status_code, 400)
        self.assertFalse(Mouvement.objects.exists())

    def test_creation_generique_entrepots_coherents(self):
        rep = self._post('/api/v1/mouvements/', {'produit': str(self.produit.pk), 'type_mouvement': 'sortie',
                                                 'quantite': '1', 'entrepot_destination': str(self.entrepot.pk)})
        self.assertEqual(rep.status_code, 400)
        self.assertFalse(Mouvement.objects.exists())

    def test_journal_non_modifiable(self):
        self._post('/api/v1/mouvements/', {'produit': str(self.produit.pk), 'type_mouvement': 'sortie',
                                           'quantite': '1', 'entrepot_source': str(self.entrepot.pk)})
        url = f'/api/v1/mouvements/{Mouvement.objects.get().pk}/'
        self.assertEqual(self.client.delete(url, **self.auth).status_code, 405)
        self.assertEqual(self.client.patch(url, '{"quantite": "9"}', content_type='application/json',
                                           **self.auth).status_code, 405)
        self.assertEqual(Mouvement.objects.get().quantite, 1)

    def test_produit_scan_expose_le_prix_de_vente(self):
        from apps.api.serializers import ProduitScanSerializer
        self.assertEqual(ProduitScanSerializer(self.produit).data['prix_vente'], '1500.00')


class RolesApiTests(EntrepriseTestCase):
    """Création de mouvements par l'API : admin entreprise, gestionnaire et magasinier uniquement."""

    def _auth(self, role):
        return {'HTTP_AUTHORIZATION': f"Bearer {RefreshToken.for_user(self.users[role]).access_token}"}

    def _creer(self, role, url='/api/v1/mouvements/rapide/'):
        donnees = ({'produit_id': str(self.produit.pk), 'type_mouvement': 'sortie', 'quantite': 1,
                    'entrepot_id': str(self.entrepot.pk)} if url.endswith('rapide/') else
                   {'produit': str(self.produit.pk), 'type_mouvement': 'sortie', 'quantite': '1',
                    'entrepot_source': str(self.entrepot.pk)})
        return self.client.post(url, json.dumps(donnees), content_type='application/json', **self._auth(role))

    def test_roles_autorises_a_creer(self):
        for role in ('admin_ent', 'gestionnaire', 'magasinier'):
            self.assertEqual(self._creer(role).status_code, 201, role)
            self.assertEqual(self._creer(role, '/api/v1/mouvements/').status_code, 201, role)
        self.assertEqual(Mouvement.objects.count(), 6)

    def test_roles_en_lecture_seule(self):
        for role in ('comptable', 'auditeur', 'responsable_achat'):
            self.assertEqual(self._creer(role).status_code, 403, role)
            self.assertEqual(self._creer(role, '/api/v1/mouvements/').status_code, 403, role)
            self.assertEqual(self.client.get('/api/v1/mouvements/', **self._auth(role)).status_code, 200, role)
        self.assertFalse(Mouvement.objects.exists())
        self.assertEqual(quantite_en_stock(self.produit, self.entrepot), 10)

    def test_detail_d_un_mouvement(self):
        self._creer('magasinier', '/api/v1/mouvements/')
        url = f'/api/v1/mouvements/{Mouvement.objects.get().pk}/'
        self.assertEqual(self.client.get(url, **self._auth('auditeur')).status_code, 200)


class AlertesApiTests(EntrepriseTestCase):

    def setUp(self):
        from apps.stock.models import Alerte
        self.alerte = Alerte.objects.create(produit=self.produit, entrepot=self.entrepot, type_alerte='rupture',
                                            priorite='critique', message='Rupture')
        self.auth = {'HTTP_AUTHORIZATION': f"Bearer {RefreshToken.for_user(self.users['magasinier']).access_token}"}
        self.url = f'/api/v1/alertes/{self.alerte.pk}/'

    def test_marquer_comme_lue(self):
        # Répondait 404 : le queryset était découpé avant la recherche de l'alerte
        self.assertEqual(self.client.get(self.url, **self.auth).status_code, 200)
        self.assertEqual(self.client.patch(self.url, '{}', content_type='application/json', **self.auth).status_code, 200)
        self.alerte.refresh_from_db()
        self.assertTrue(self.alerte.lue)

    def test_creation_et_suppression_refusees(self):
        from apps.stock.models import Alerte
        autre = creer_produit(creer_entreprise('B'))
        rep = self.client.post('/api/v1/alertes/', json.dumps({
            'produit': str(autre.pk), 'type_alerte': 'rupture', 'priorite': 'critique', 'message': 'x',
        }), content_type='application/json', **self.auth)
        self.assertEqual(rep.status_code, 405)
        self.assertEqual(self.client.delete(self.url, **self.auth).status_code, 405)
        self.assertEqual(Alerte.objects.count(), 1)
        self.assertEqual(self.client.get('/api/v1/alertes/compteur/', **self.auth).json(), {'non_lues': 1})


class ProduitsApiTests(EntrepriseTestCase):

    def _req(self, methode, role, url='/api/v1/produits/', donnees=None):
        auth = {'HTTP_AUTHORIZATION': f"Bearer {RefreshToken.for_user(self.users[role]).access_token}"}
        if methode == 'get':
            return self.client.get(url, **auth)
        return getattr(self.client, methode)(url, json.dumps(donnees or {}), content_type='application/json', **auth)

    def test_creation_par_le_gestionnaire(self):
        from apps.stock.models import Produit
        rep = self._req('post', 'gestionnaire', donnees={'nom': 'Sucre', 'sku': 'SUC-1', 'prix_unitaire': '300',
                                                         'unite_mesure': 'kg'})
        self.assertEqual(rep.status_code, 201, rep.content)
        self.assertEqual(Produit.objects.get(sku='SUC-1').entreprise, self.ent)  # plantait : entreprise absente

    def test_sku_en_double_refuse_sans_erreur_serveur(self):
        rep = self._req('post', 'gestionnaire', donnees={'nom': 'Autre', 'sku': self.produit.sku, 'prix_unitaire': '1'})
        self.assertEqual(rep.status_code, 400)

    def test_ecriture_refusee_aux_autres_roles(self):
        url = f'/api/v1/produits/{self.produit.pk}/'
        for role in ('magasinier', 'comptable', 'auditeur', 'responsable_achat'):
            self.assertEqual(self._req('patch', role, url, {'nom': 'X'}).status_code, 403, role)
            self.assertEqual(self._req('delete', role, url).status_code, 403, role)
            self.assertEqual(self._req('get', role, url).status_code, 200, role)

    def test_suppression_archive_le_produit(self):
        from apps.stock.models import Produit
        rep = self._req('delete', 'admin_ent', f'/api/v1/produits/{self.produit.pk}/')
        self.assertEqual(rep.status_code, 204)
        self.assertFalse(Produit.objects.get(pk=self.produit.pk).est_actif)  # conservé avec son historique

    def test_categorie_d_une_autre_entreprise_refusee(self):
        from apps.stock.models import Categorie
        cat = Categorie.objects.create(nom='Étrangère', entreprise=creer_entreprise('B'))
        rep = self._req('patch', 'gestionnaire', f'/api/v1/produits/{self.produit.pk}/', {'categorie': str(cat.pk)})
        self.assertEqual(rep.status_code, 400)
