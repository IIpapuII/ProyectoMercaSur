# inventarios/services/icg_integration.py
def enviar_orden_a_icg(orden) -> tuple[bool, str | None, str]:
    """
    Stub: aquí vas a llamar tu SP o inserción masiva en ICG.
    Devuelve (exito, id_orden_icg, mensaje).
    """
    # TODO: Implementar pyodbc + SP INSERT_OC con las líneas de 'orden'
    # Por ahora simulamos:
    fake_id = f"ICG-{orden.numero_orden}"
    return True, fake_id, "Orden enviada a ICG (simulada)."
