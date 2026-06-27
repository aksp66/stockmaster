from django.urls import path
from . import views
 
app_name = "ia"
 
urlpatterns = [
    path("",                       views.predictions_dashboard,    name="predictions_dashboard"),
    path("lancer/",                views.lancer_analyse,           name="lancer_analyse"),
    path("statut/<str:task_id>/",  views.statut_tache,             name="statut_tache"),
    path("produit/<int:produit_id>/", views.prediction_detail,     name="prediction_detail"),
    path("suggestion/<int:suggestion_id>/valider/",
         views.valider_suggestion, name="valider_suggestion"),
    path("api/graphique/",         views.api_graphique_predictions, name="api_graphique"),
]