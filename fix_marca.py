import re

# Leer el archivo
with open('/Users/iipapuii/Pictures/PROYECTOS/ProyectoMercaSur/Compras/services/icg_import.py', 'r') as f:
    content = f.read()

# Reemplazar la línea 265
old_line = "        consulta += f\"      AND MC.DESCRIPCION = '{marca.replace(\"'\", \"''\")}'\n\""
new_lines = """        marcas_escaped = [m.replace("'", "''") for m in marcas_list]
        marcas_str = "', '".join(marcas_escaped)
        consulta += f"      AND MC.DESCRIPCION IN ('{marcas_str}')\\n\""""

content = content.replace(old_line, new_lines)

# Escribir el archivo
with open('/Users/iipapuii/Pictures/PROYECTOS/ProyectoMercaSur/Compras/services/icg_import.py', 'w') as f:
    f.write(content)

print("Archivo actualizado")
