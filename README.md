# PetProject (Flet, compat) — Login → Dashboard + Drawer + Mis Mascotas

- **Compat:** no usa `flet.icons` ni `flet.colors` (iconos por nombre y colores hex).
- **Mis Mascotas:** listado con SQLite, estado vacío, tarjeta con foto, botones *Mapa*, *QR*, *Eliminar* y FAB *Agregar*.
- **Drawer:** saludo arriba y opción “Mis Mascotas”.

## Ejecutar (venv activo)
```powershell
python main.py
# o:
# .\.venv\Scripts\python.exe main.py
```
Credenciales demo: `admin@admin.cl` / `admin123` (en `pages/login.py`).

## Estructura
```
├─ main.py
├─ routes.py
├─ services/
│  ├─ db.py
│  └─ __init__.py
├─ pages/
│  ├─ login.py
│  ├─ dashboard.py
│  ├─ pets.py
│  └─ __init__.py
├─ ui/
│  ├─ components.py
│  └─ __init__.py
├─ assets/
│  ├─ logo_paw.svg
│  └─ dog.jpg
└─ requirements.txt
```