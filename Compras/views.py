# views.py
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from .models import AsignacionMarcaVendedor, Proveedor, Marca

@staff_member_required
@require_http_methods(["GET"])
def api_marcas_por_proveedor(request):
    """
    API endpoint que devuelve marcas en formato JSON para Select2.

    Filtros:
      - proveedor_id (o proveedor)  -> requerido para filtrar las asignaciones
      - request.user.perfil_vendedor -> restringe a marcas asignadas a ese vendedor
      - request.user.perfil_proveedor -> garantiza coherencia: solo ese proveedor
      - q (opcional) -> búsqueda por nombre de marca (icontains)
      - limit (opcional) -> cuántos resultados devolver (por defecto 100)
    """

    print("=== DEBUG API MARCAS POR PROVEEDOR (VIEW) ===")
    print(f"Método: {request.method}")
    print(f"GET params: {dict(request.GET)}")
    print(f"Usuario: {request.user}")

    proveedor_id = request.GET.get("proveedor_id") or request.GET.get("proveedor")
    termino = request.GET.get("q")  # para búsquedas de Select2
    try:
      limit = int(request.GET.get("limit") or 100)
    except ValueError:
      limit = 100

    print(f"Proveedor ID recibido: {proveedor_id}")
    print(f"Término de búsqueda: {termino!r}")
    print(f"Limit: {limit}")

    if not proveedor_id:
        print("No hay proveedor_id, devolviendo lista vacía")
        return JsonResponse({"marcas": [], "count": 0})

    # Verificar proveedor
    try:
        proveedor = Proveedor.objects.get(pk=proveedor_id)
        print(f"Proveedor encontrado: {proveedor.nombre}")
    except Proveedor.DoesNotExist:
        print(f"Proveedor ID {proveedor_id} no existe")
        return JsonResponse({"error": "Proveedor no encontrado"}, status=404)

    # Perfiles del usuario
    perfil_prov = getattr(request.user, "perfil_proveedor", None)
    perfil_vend = getattr(request.user, "perfil_vendedor", None)
    print(f"Perfil proveedor (usuario): {perfil_prov}")
    print(f"Perfil vendedor (usuario): {perfil_vend}")

    # Si el usuario tiene perfil_proveedor, validamos que corresponda
    if perfil_prov and perfil_prov.proveedor_id != proveedor.id:
        print("Proveedor del perfil del usuario no coincide con el solicitado. Retornando vacío por seguridad.")
        return JsonResponse({"marcas": [], "count": 0})

    # Base: asignaciones por proveedor
    asignaciones = AsignacionMarcaVendedor.objects.filter(proveedor_id=proveedor.id)
    print(f"Asignaciones base por proveedor: {asignaciones.count()}")

    # Si tiene perfil_vendedor, restringimos a sus asignaciones
    if perfil_vend:
        asignaciones = asignaciones.filter(vendedor=perfil_vend)
        print(f"Asignaciones tras filtrar por vendedor {perfil_vend}: {asignaciones.count()}")

    # IDs de marcas a partir de las asignaciones filtradas
    marca_ids = asignaciones.values_list("marca_id", flat=True).distinct()
    print(f"IDs de marcas candidatos: {list(marca_ids)}")

    # QuerySet de marcas
    qs = Marca.objects.filter(pk__in=marca_ids)

    # Término de búsqueda opcional (Select2)
    if termino:
        qs = qs.filter(nombre__icontains=termino)

    qs = qs.order_by("nombre").distinct()

    total = qs.count()
    print(f"Marcas finales tras filtros y búsqueda: {total}")

    # Si se pidió limit, aplicarlo (útil para Select2)
    if limit and limit > 0:
        qs = qs[:limit]

    # Formato Select2
    marcas_data = []
    for marca in qs:
        item = {
            "id": marca.id,
            "text": marca.nombre,  # texto que muestra Select2
            "nombre": marca.nombre
        }
        marcas_data.append(item)
        print(f"  - Marca: {marca.nombre} (ID: {marca.id})")

    resultado = {
        "marcas": marcas_data,
        "count": total,
        "proveedor": {
            "id": proveedor.id,
            "nombre": proveedor.nombre,
        },
        # Por si quieres depurar en el front:
        "usuario": str(request.user),
        "limit_applied": limit if (limit and limit > 0) else None,
    }
    print(f"Resultado final: {resultado}")
    print("=== END DEBUG API ===")
    return JsonResponse(resultado)
