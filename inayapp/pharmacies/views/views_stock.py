# pharmacies/views/view_stock.py
from datetime import timezone
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView
from datetime import timedelta
from django.utils import timezone
from ..models import Stock
from django.utils import timezone
from django.views.generic import (
    CreateView,
    ListView,
    UpdateView,
    DetailView,
    DeleteView,
)
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.db.models import Q, Sum
from ..models import Stock, Produit, AjustementStock, MouvementStock
from ..forms import StockForm, AjustementStockForm


class StockListView(LoginRequiredMixin, ListView):
    model = Stock
    template_name = "stock/stock_list.html"
    context_object_name = "stocks"
    paginate_by = 20

    def get_queryset(self):
        queryset = Stock.objects.select_related("produit", "service").filter(
            quantite__gt=0
        )

        # Filtres de recherche
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(
                Q(produit__nom__icontains=search)
                | Q(produit__code_produit__icontains=search)
                | Q(service__name__icontains=search)
            )

        service = self.request.GET.get("service")
        if service:
            queryset = queryset.filter(service_id=service)

        # Stocks périmés ou bientôt périmés
        filter_expiry = self.request.GET.get("expiry")
        if filter_expiry == "expired":
            queryset = queryset.filter(date_peremption__lt=timezone.now().date())
        elif filter_expiry == "soon":
            from datetime import timedelta

            soon_date = timezone.now().date() + timedelta(days=30)
            queryset = queryset.filter(
                date_peremption__lte=soon_date,
                date_peremption__gte=timezone.now().date(),
            )

        return queryset.order_by("date_peremption", "produit__nom")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Ajouter les services pour le filtre
        from medical.models import Service

        today = timezone.now().date()
        context["today"] = today
        context["soon_date"] = today + timedelta(days=30)
        context["services"] = Service.objects.all().order_by("name")

        # Statistiques rapides
        context["total_stocks"] = Stock.objects.filter(quantite__gt=0).count()
        context["stocks_expires"] = Stock.objects.filter(
            date_peremption__lt=timezone.now().date()
        ).count()
        context["stocks_bientot_expires"] = Stock.objects.filter(
            date_peremption__lte=timezone.now().date() + timezone.timedelta(days=30),
            date_peremption__gte=timezone.now().date(),
        ).count()

        return context


class StockCreateView(LoginRequiredMixin, CreateView):
    model = Stock
    form_class = StockForm
    template_name = "stock/stock_form.html"
    success_url = reverse_lazy("pharmacies:stock_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["produits"] = Produit.objects.all().order_by("nom")
        from medical.models import Service

        context["services"] = Service.objects.all().order_by("name")
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                # Utiliser le manager pour gérer les stocks existants
                stock = Stock.objects.update_or_create_stock(
                    produit=form.cleaned_data["produit"],
                    service=form.cleaned_data["service"],
                    date_peremption=form.cleaned_data["date_peremption"],
                    numero_lot=form.cleaned_data["numero_lot"] or "",
                    quantite=form.cleaned_data["quantite"],
                )

                # Log du mouvement
                MouvementStock.log_mouvement(
                    instance=stock,
                    type_mouvement="ENTREE",
                    produit=stock.produit,
                    service=stock.service,
                    quantite=form.cleaned_data["quantite"],
                    lot_concerne=stock.numero_lot,
                )

                messages.success(
                    self.request,
                    f"Stock ajouté avec succès: {stock.quantite} unités de {stock.produit}",
                )
                return redirect(self.success_url)

        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


class StockDetailView(LoginRequiredMixin, DetailView):
    model = Stock
    template_name = "stock/stock_detail.html"
    context_object_name = "stock"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Historique des mouvements pour ce stock
        context["mouvements"] = MouvementStock.objects.filter(
            produit=self.object.produit, service=self.object.service
        ).order_by("-date_mouvement")[:10]

        # Vérifier si périmé
        context["is_expired"] = self.object.date_peremption < timezone.now().date()

        return context


class StockUpdateView(LoginRequiredMixin, UpdateView):
    model = Stock
    form_class = StockForm
    template_name = "stock/stock_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["produits"] = Produit.objects.all().order_by("nom")
        from medical.models import Service

        context["services"] = Service.objects.all().order_by("name")
        return context

    def form_valid(self, form):
        messages.success(self.request, "Stock modifié avec succès")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("pharmacies:stock_detail", kwargs={"pk": self.object.pk})


class StockDeleteView(LoginRequiredMixin, DeleteView):
    model = Stock
    template_name = "stock/stock_confirm_delete.html"
    success_url = reverse_lazy("pharmacies:stock_list")

    def delete(self, request, *args, **kwargs):
        stock = self.get_object()
        messages.success(request, f"Stock supprimé: {stock.produit} - {stock.service}")
        return super().delete(request, *args, **kwargs)


# ==================== AJUSTEMENTS ====================


class AjustementStockCreateView(LoginRequiredMixin, CreateView):
    model = AjustementStock
    form_class = AjustementStockForm
    template_name = "stock/ajustement_form.html"
    success_url = reverse_lazy("pharmacies:stock_list")

    def get_initial(self):
        initial = super().get_initial()
        stock_id = self.request.GET.get("stock")
        if stock_id:
            stock = get_object_or_404(Stock, pk=stock_id)
            initial["stock"] = stock
            initial["quantite_avant"] = stock.quantite
        return initial

    def form_valid(self, form):
        try:
            with transaction.atomic():
                ajustement = form.save(commit=False)
                ajustement.responsable = self.request.user.personnel
                ajustement.save()

                # Mettre à jour le stock
                stock = ajustement.stock
                stock.quantite = ajustement.quantite_apres
                stock.save()

                messages.success(
                    self.request,
                    f"Ajustement effectué: {stock.produit} "
                    f"({ajustement.quantite_avant} → {ajustement.quantite_apres})",
                )
                return redirect(self.success_url)

        except Exception as e:
            form.add_error(None, f"Erreur lors de l'ajustement: {str(e)}")
            return self.form_invalid(form)


# ==================== VUES AJAX ====================


def get_stock_disponible(request):
    """API pour récupérer le stock disponible d'un produit dans un service"""
    produit_id = request.GET.get("produit_id")
    service_id = request.GET.get("service_id")

    if not produit_id or not service_id:
        return JsonResponse({"error": "Paramètres manquants"}, status=400)

    try:
        produit = Produit.objects.get(pk=produit_id)
        from medical.models import Service

        service = Service.objects.get(pk=service_id)

        stocks = Stock.objects.get_available(produit, service)
        total_disponible = stocks.aggregate(total=Sum("quantite"))["total"] or 0

        stocks_data = []
        for stock in stocks[:5]:  # Limiter à 5 lots
            stocks_data.append(
                {
                    "id": stock.id,
                    "quantite": stock.quantite,
                    "date_peremption": (
                        stock.date_peremption.strftime("%d/%m/%Y")
                        if stock.date_peremption
                        else ""
                    ),
                    "numero_lot": stock.numero_lot or "N/A",
                }
            )

        return JsonResponse(
            {"total_disponible": total_disponible, "stocks": stocks_data}
        )

    except (Produit.DoesNotExist, Service.DoesNotExist):
        return JsonResponse({"error": "Produit ou service introuvable"}, status=404)


def stocks_expires_bientot(request):
    """API pour récupérer les stocks qui expirent bientôt"""
    from datetime import timedelta

    dans_jours = int(request.GET.get("jours", 30))
    date_limite = timezone.now().date() + timedelta(days=dans_jours)

    stocks = (
        Stock.objects.filter(
            date_peremption__lte=date_limite,
            date_peremption__gte=timezone.now().date(),
            quantite__gt=0,
        )
        .select_related("produit", "service")
        .order_by("date_peremption")
    )

    data = []
    for stock in stocks:
        jours_restants = (stock.date_peremption - timezone.now().date()).days
        data.append(
            {
                "id": stock.id,
                "produit": stock.produit.nom,
                "service": stock.service.name,
                "quantite": stock.quantite,
                "date_peremption": stock.date_peremption.strftime("%d/%m/%Y"),
                "jours_restants": jours_restants,
                "numero_lot": stock.numero_lot or "N/A",
            }
        )

    return JsonResponse({"stocks": data})
