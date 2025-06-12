# inventaire/serializers.py
from rest_framework import serializers
from .models import *


class SalleSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = Salle
        fields = "__all__"


class CategorieItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategorieItem
        fields = "__all__"


class MarqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marque
        fields = "__all__"


class ItemSerializer(serializers.ModelSerializer):
    categorie_nom = serializers.CharField(source="categorie.nom", read_only=True)
    marque_nom = serializers.CharField(source="marque.nom", read_only=True)
    est_sous_garantie = serializers.BooleanField(read_only=True)

    class Meta:
        model = Item
        fields = "__all__"


class StockSerializer(serializers.ModelSerializer):
    item_nom = serializers.CharField(source="item.nom", read_only=True)
    salle_nom = serializers.CharField(source="salle.nom", read_only=True)
    service_nom = serializers.CharField(source="salle.service.name", read_only=True)
    est_en_alerte = serializers.BooleanField(read_only=True)
    est_en_rupture = serializers.BooleanField(read_only=True)

    class Meta:
        model = Stock
        fields = "__all__"


class MouvementStockSerializer(serializers.ModelSerializer):
    item_nom = serializers.CharField(source="stock.item.nom", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True
    )

    class Meta:
        model = MouvementStock
        fields = "__all__"


class DemandeTransfertSerializer(serializers.ModelSerializer):
    item_nom = serializers.CharField(source="item.nom", read_only=True)
    salle_source_nom = serializers.CharField(source="salle_source.nom", read_only=True)
    salle_destination_nom = serializers.CharField(
        source="salle_destination.nom", read_only=True
    )
    demande_par_name = serializers.CharField(
        source="demande_par.username", read_only=True
    )

    class Meta:
        model = DemandeTransfert
        fields = "__all__"


class LigneInventaireSerializer(serializers.ModelSerializer):
    item_nom = serializers.CharField(source="stock.item.nom", read_only=True)
    ecart = serializers.IntegerField(read_only=True)
    statut_ecart = serializers.CharField(read_only=True)

    class Meta:
        model = LigneInventaire
        fields = "__all__"


class InventaireSerializer(serializers.ModelSerializer):
    salle_nom = serializers.CharField(source="salle.nom", read_only=True)
    responsable_name = serializers.CharField(
        source="responsable.username", read_only=True
    )
    lignes_inventaire = LigneInventaireSerializer(many=True, read_only=True)

    class Meta:
        model = Inventaire
        fields = "__all__"
