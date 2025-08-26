# services/rappi_missing.py
from django.db import transaction
from ..models import MissingRappiProduct

def log_missing_product(*, articulo, store_name: str | None, rappi_store_id: int | None,
                        error: str, lookups_debug: dict | list | None = None) -> None:
    """
    Crea/actualiza un MissingRappiProduct cuando no se encuentra el item en Rappi.
    """
    defaults = {
        "code": getattr(articulo, "code", None),
        "store_name": store_name,
        "rappi_store_id": rappi_store_id,
        "name": getattr(articulo, "name", None),
        "price": getattr(articulo, "price", 0) or 0,
        "discount_price": getattr(articulo, "discount_price", 0) or 0,
        "stock": getattr(articulo, "stock", 0) or 0,
        "last_error": error[:2000],  # evita textos gigantes
        "lookups_debug": lookups_debug,
        "flagged_for_creation": True,
        "resolved": False,
    }
    with transaction.atomic():
        obj, created = MissingRappiProduct.objects.select_for_update().get_or_create(
            ean=getattr(articulo, "ean", None) or "",
            store_local_id=str(getattr(articulo, "store_id", "")),
            defaults=defaults,
        )
        if not created:
            # incrementa intentos y actualiza info reciente
            obj.attempts = (obj.attempts or 0) + 1
            for k, v in defaults.items():
                setattr(obj, k, v)
            obj.save()
