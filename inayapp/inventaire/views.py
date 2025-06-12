# inventaire/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    TemplateView,
)
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum, Count
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import *
from .serializers import *
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import qrcode


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Statistiques générales
        context["total_items"] = Item.objects.count()
        context["total_stocks"] = Stock.objects.count()
        context["stocks_alerte"] = Stock.objects.filter(
            quantite__lte=models.F("quantite_min")
        ).count()
        context["stocks_rupture"] = Stock.objects.filter(quantite=0).count()

        # Mouvements récents
        context["mouvements_recents"] = MouvementStock.objects.select_related(
            "stock__item"
        ).order_by("-date_mouvement")[:10]

        # Demandes de transfert en attente
        context["transferts_attente"] = DemandeTransfert.objects.filter(
            statut="en_attente"
        ).count()

        # Équipements en maintenance
        context["maintenances_cours"] = MaintenanceEquipement.objects.filter(
            statut="en_cours"
        ).count()

        return context


class StockListView(LoginRequiredMixin, ListView):
    model = Stock
    template_name = "stock_list.html"
    context_object_name = "stocks"
    paginate_by = 50

    def get_queryset(self):
        queryset = Stock.objects.select_related("item", "salle", "salle__service")

        # Filtres
        search = self.request.GET.get("search")
        service = self.request.GET.get("service")
        salle = self.request.GET.get("salle")
        alerte = self.request.GET.get("alerte")

        if search:
            queryset = queryset.filter(
                Q(item__nom__icontains=search)
                | Q(item__code_barre__icontains=search)
                | Q(salle__nom__icontains=search)
            )

        if service:
            queryset = queryset.filter(salle__service_id=service)

        if salle:
            queryset = queryset.filter(salle_id=salle)

        if alerte == "true":
            queryset = queryset.filter(quantite__lte=models.F("quantite_min"))

        return queryset.order_by("item__nom")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from medical.models import Service

        context["services"] = Service.objects.all()
        context["salles"] = Salle.objects.all()
        return context


class StockAlertsView(LoginRequiredMixin, ListView):
    model = Stock
    template_name = "stock_alerts.html"
    context_object_name = "stocks_alerte"

    def get_queryset(self):
        return (
            Stock.objects.filter(quantite__lte=models.F("quantite_min"))
            .select_related("item", "salle", "salle__service")
            .order_by("quantite")
        )


class StockDetailView(LoginRequiredMixin, DetailView):
    model = Stock
    template_name = "stock_detail.html"
    context_object_name = "stock"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["mouvements"] = self.object.mouvements.order_by("-date_mouvement")[:20]
        return context


class MouvementListView(LoginRequiredMixin, ListView):
    model = MouvementStock
    template_name = "mouvement_list.html"
    context_object_name = "mouvements"
    paginate_by = 50

    def get_queryset(self):
        return MouvementStock.objects.select_related(
            "stock__item", "stock__salle", "created_by"
        ).order_by("-date_mouvement")


class MouvementCreateView(LoginRequiredMixin, CreateView):
    model = MouvementStock
    template_name = "mouvement_form.html"
    fields = [
        "stock",
        "type_mouvement",
        "quantite",
        "salle_destination",
        "motif",
        "cout_reparation",
    ]

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class TransfertListView(LoginRequiredMixin, ListView):
    model = DemandeTransfert
    template_name = "transfert_list.html"
    context_object_name = "transferts"
    paginate_by = 50


class TransfertCreateView(LoginRequiredMixin, CreateView):
    model = DemandeTransfert
    template_name = "transfert_form.html"
    fields = ["item", "salle_source", "salle_destination", "quantite", "motif"]

    def form_valid(self, form):
        form.instance.demande_par = self.request.user
        return super().form_valid(form)


class TransfertApproveView(LoginRequiredMixin, DetailView):
    model = DemandeTransfert

    def post(self, request, *args, **kwargs):
        transfert = self.get_object()
        action = request.POST.get("action")

        if action == "approve":
            transfert.approuver(request.user)
            messages.success(request, "Demande de transfert approuvée")
        elif action == "execute":
            try:
                transfert.executer(request.user)
                messages.success(request, "Transfert exécuté avec succès")
            except Exception as e:
                messages.error(request, f"Erreur lors de l'exécution: {str(e)}")
        elif action == "refuse":
            transfert.statut = "refuse"
            transfert.save()
            messages.warning(request, "Demande de transfert refusée")

        return redirect("inventaire:transfert_list")


class InventaireListView(LoginRequiredMixin, ListView):
    model = Inventaire
    template_name = "inventaire_list.html"
    context_object_name = "inventaires"
    paginate_by = 20


class InventaireCreateView(LoginRequiredMixin, CreateView):
    model = Inventaire
    template_name = "inventaire_form.html"
    fields = ["nom", "salle", "date_planifiee", "participants", "observations"]

    def form_valid(self, form):
        form.instance.responsable = self.request.user
        return super().form_valid(form)


class InventaireDetailView(LoginRequiredMixin, DetailView):
    model = Inventaire
    template_name = "inventaire_detail.html"
    context_object_name = "inventaire"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lignes"] = self.object.lignes_inventaire.select_related("stock__item")
        return context

    def post(self, request, *args, **kwargs):
        inventaire = self.get_object()
        action = request.POST.get("action")

        if action == "start":
            inventaire.demarrer()
            messages.success(request, "Inventaire démarré")
        elif action == "finish":
            inventaire.terminer()
            messages.success(request, "Inventaire terminé")
        elif action == "validate":
            inventaire.valider()
            messages.success(request, "Inventaire validé et stocks ajustés")

        return redirect("inventaire:inventaire_detail", pk=inventaire.pk)


class StockReportView(LoginRequiredMixin, TemplateView):
    template_name = "stock_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Rapport par service
        from medical.models import Service

        services_data = []
        for service in Service.objects.all():
            stocks = Stock.objects.filter(salle__service=service)
            services_data.append(
                {
                    "service": service,
                    "total_items": stocks.count(),
                    "valeur_totale": stocks.aggregate(
                        total=Sum(models.F("quantite") * models.F("item__prix_achat"))
                    )["total"]
                    or 0,
                    "alertes": stocks.filter(
                        quantite__lte=models.F("quantite_min")
                    ).count(),
                }
            )

        context["services_data"] = services_data

        # Top 10 des items les plus coûteux
        context["items_couteux"] = Item.objects.filter(
            prix_achat__isnull=False
        ).order_by("-prix_achat")[:10]

        return context


class MovementReportView(LoginRequiredMixin, TemplateView):
    template_name = "movement_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Mouvements par type
        context["mouvements_par_type"] = (
            MouvementStock.objects.values("type_mouvement")
            .annotate(count=Count("id"), quantite_totale=Sum("quantite"))
            .order_by("-count")
        )

        return context


class BarcodeScanView(LoginRequiredMixin, TemplateView):
    template_name = "barcode_scan.html"

    def post(self, request, *args, **kwargs):
        code_barre = request.POST.get("code_barre")
        try:
            item = Item.objects.get(code_barre=code_barre)
            stocks = Stock.objects.filter(item=item).select_related("salle")

            return JsonResponse(
                {
                    "success": True,
                    "item": {
                        "id": item.id,
                        "nom": item.nom,
                        "code_barre": item.code_barre,
                        "categorie": item.categorie.nom,
                        "etat": item.get_etat_display(),
                    },
                    "stocks": [
                        {
                            "id": stock.id,
                            "salle": stock.salle.nom,
                            "service": stock.salle.service.name,
                            "quantite": stock.quantite,
                        }
                        for stock in stocks
                    ],
                }
            )
        except Item.DoesNotExist:
            return JsonResponse({"success": False, "error": "Item non trouvé"})


class BarcodeGenerateView(LoginRequiredMixin, DetailView):
    model = Item

    def get(self, request, *args, **kwargs):
        item = self.get_object()

        # Générer le QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(item.code_barre)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Créer le PDF
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)

        # Titre
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, 750, f"Code-barres: {item.nom}")

        # Informations item
        p.setFont("Helvetica", 12)
        y = 700
        p.drawString(100, y, f"Code-barres: {item.code_barre}")
        y -= 20
        p.drawString(100, y, f"Catégorie: {item.categorie.nom}")
        y -= 20
        if item.marque:
            p.drawString(100, y, f"Marque: {item.marque.nom}")
            y -= 20

        # Convertir l'image QR en string pour l'intégrer au PDF
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="PNG")
        img_buffer.seek(0)

        # Dessiner le QR code
        p.drawInlineImage(img_buffer, 100, y - 200, width=200, height=200)

        p.showPage()
        p.save()

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="barcode_{item.code_barre}.pdf"'
        )

        return response


# API ViewSets pour l'intégration mobile/web
class SalleViewSet(viewsets.ModelViewSet):
    queryset = Salle.objects.all()
    serializer_class = SalleSerializer


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer

    @action(detail=False, methods=["get"])
    def search_by_barcode(self, request):
        code_barre = request.query_params.get("code_barre")
        if code_barre:
            try:
                item = Item.objects.get(code_barre=code_barre)
                serializer = self.get_serializer(item)
                return Response(serializer.data)
            except Item.DoesNotExist:
                return Response(
                    {"error": "Item non trouvé"}, status=status.HTTP_404_NOT_FOUND
                )
        return Response(
            {"error": "Code-barres requis"}, status=status.HTTP_400_BAD_REQUEST
        )


class StockViewSet(viewsets.ModelViewSet):
    queryset = Stock.objects.all()
    serializer_class = StockSerializer

    @action(detail=False, methods=["get"])
    def alerts(self, request):
        stocks_alerte = Stock.objects.filter(quantite__lte=models.F("quantite_min"))
        serializer = self.get_serializer(stocks_alerte, many=True)
        return Response(serializer.data)


class MouvementStockViewSet(viewsets.ModelViewSet):
    queryset = MouvementStock.objects.all()
    serializer_class = MouvementStockSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class DemandeTransfertViewSet(viewsets.ModelViewSet):
    queryset = DemandeTransfert.objects.all()
    serializer_class = DemandeTransfertSerializer

    def perform_create(self, serializer):
        serializer.save(demande_par=self.request.user)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        transfert = self.get_object()
        transfert.approuver(request.user)
        return Response({"status": "approved"})

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        transfert = self.get_object()
        try:
            transfert.executer(request.user)
            return Response({"status": "executed"})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventaireViewSet(viewsets.ModelViewSet):
    queryset = Inventaire.objects.all()
    serializer_class = InventaireSerializer

    def perform_create(self, serializer):
        serializer.save(responsable=self.request.user)


class MaintenanceListView(LoginRequiredMixin, ListView):
    model = MaintenanceEquipement
    template_name = "maintenance_list.html"
    context_object_name = "maintenances"
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filtres
        type_maintenance = self.request.GET.get("type")
        statut = self.request.GET.get("statut")
        technicien = self.request.GET.get("technicien")

        if type_maintenance:
            queryset = queryset.filter(type_maintenance=type_maintenance)
        if statut:
            queryset = queryset.filter(statut=statut)
        if technicien:
            queryset = queryset.filter(technicien_id=technicien)

        return queryset.select_related("item", "technicien").order_by("-date_planifiee")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["techniciens"] = User.objects.filter(
            maintenances_technicien__isnull=False
        ).distinct()
        return context


class MaintenanceCreateView(LoginRequiredMixin, CreateView):
    model = MaintenanceEquipement
    template_name = "maintenance_form.html"
    fields = [
        "item",
        "type_maintenance",
        "titre",
        "description",
        "date_planifiee",
        "technicien",
        "cout",
        "observations",
    ]

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class MaintenanceDetailView(LoginRequiredMixin, DetailView):
    model = MaintenanceEquipement
    template_name = "maintenance_detail.html"
    context_object_name = "maintenance"

    def post(self, request, *args, **kwargs):
        maintenance = self.get_object()
        action = request.POST.get("action")
        user = request.user

        if action == "start" and maintenance.statut == "planifiee":
            maintenance.demarrer(user)
            messages.success(request, "Maintenance démarrée avec succès")

        elif action == "finish" and maintenance.statut == "en_cours":
            rapport = request.POST.get("rapport", "")
            pieces_changees = request.POST.get("pieces_changees", "")
            nouveau_etat = request.POST.get("nouveau_etat", "bon")

            maintenance.terminer(rapport, nouveau_etat)
            maintenance.pieces_changees = pieces_changees
            maintenance.save()

            messages.success(request, "Maintenance terminée avec succès")

        elif action == "cancel":
            maintenance.statut = "annulee"
            maintenance.save()
            messages.warning(request, "Maintenance annulée")

        return redirect("inventaire:maintenance_detail", pk=maintenance.pk)


class MaintenanceUpdateView(LoginRequiredMixin, UpdateView):
    model = MaintenanceEquipement
    template_name = "maintenance_form.html"
    fields = [
        "item",
        "type_maintenance",
        "titre",
        "description",
        "date_planifiee",
        "technicien",
        "cout",
        "observations",
    ]


class MouvementStockDetailView(LoginRequiredMixin, DetailView):
    model = MouvementStock
    template_name = "mouvement_detail.html"
    context_object_name = "mouvement"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mouvement = self.object

        # Ajouter des détails supplémentaires
        context["item"] = mouvement.stock.item
        context["salle_source"] = mouvement.stock.salle

        if mouvement.salle_destination:
            context["salle_destination"] = mouvement.salle_destination

        return context


class TransfertDetailView(LoginRequiredMixin, DetailView):
    model = DemandeTransfert
    template_name = "transfert_detail.html"
    context_object_name = "transfert"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transfert = self.object

        # Vérifier le stock disponible
        try:
            stock_source = Stock.objects.get(
                item=transfert.item, salle=transfert.salle_source
            )
            context["stock_disponible"] = stock_source.quantite
        except Stock.DoesNotExist:
            context["stock_disponible"] = 0

        return context

    def post(self, request, *args, **kwargs):
        transfert = self.get_object()
        action = request.POST.get("action")

        if action == "approve":
            transfert.approuver(request.user)
            messages.success(request, "Demande de transfert approuvée")

        elif action == "execute":
            try:
                transfert.executer(request.user)
                messages.success(request, "Transfert exécuté avec succès")
            except Exception as e:
                messages.error(request, f"Erreur: {str(e)}")

        elif action == "refuse":
            transfert.statut = "refuse"
            transfert.save()
            messages.warning(request, "Demande de transfert refusée")

        return redirect("inventaire:transfert_detail", pk=transfert.pk)
