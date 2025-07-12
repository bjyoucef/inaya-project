class StockManager(models.Manager):
    def get_available(self, produit, service):
        """Retourne les stocks disponibles (non périmés) pour un produit dans un service"""
        return self.filter(
            produit=produit,
            service=service,
            quantite__gt=0,
            date_peremption__gte=timezone.now().date(),
        ).order_by("date_peremption")

    def get_stock_disponible(self, produit, service):
        """Retourne la quantité totale disponible pour un produit dans un service"""
        return (
            self.get_available(produit, service).aggregate(
                total=models.Sum("quantite")
            )["total"]
            or 0
        )

    def update_or_create_stock(
        self, produit, service, date_peremption, numero_lot, quantite
    ):
        with transaction.atomic():
            stock, created = self.select_for_update().get_or_create(
                produit=produit,
                service=service,
                date_peremption=date_peremption,
                numero_lot=numero_lot,
                defaults={"quantite": quantite},
            )

            if not created:
                stock.quantite += quantite
                stock.save()

            return stock
