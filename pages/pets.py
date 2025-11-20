# pages/pets.py
import io
import os
import uuid
import json
import base64
import traceback
import urllib.request
import urllib.error
import urllib.parse as _url

import flet as ft
from services import db
from ui.components import page_preset, PRIMARY, MUTED

# -------------------- Config --------------------

DEFAULT_PHOTO_WEB = "/assets/dog.jpg"      # cuando la ruta web funciona
DEFAULT_PHOTO_FS  = "assets/dog.jpg"       # fallback local si existe
UPLOADS_DIR = os.path.abspath("uploads/pets")


# -------------------- Helpers plataforma / rutas --------------------

def _platform_str(page: ft.Page) -> str:
    p = getattr(page, "platform", None)
    if p is None:
        return ""
    v = getattr(p, "value", None)
    if isinstance(v, str):
        return v.lower()
    return str(p).lower()


def _default_photo(page: ft.Page) -> str:
    """Devuelve un path válido según plataforma."""
    if _platform_str(page) == "web":
        return DEFAULT_PHOTO_WEB
    return DEFAULT_PHOTO_FS if os.path.exists(DEFAULT_PHOTO_FS) else DEFAULT_PHOTO_WEB


# -------------------- Abrir / Cerrar diálogos (compat Flet viejo/nuevo) --------------------

def _open_dialog(page: ft.Page, dlg: ft.AlertDialog):
    try:
        page.open(dlg)        # Flet recientes
    except Exception:
        page.dialog = dlg     # Flet antiguos
        dlg.open = True
        page.update()


def _close_dialog(page: ft.Page, dlg: ft.AlertDialog):
    try:
        page.close(dlg)       # Flet recientes
    except Exception:
        dlg.open = False      # Flet antiguos
        page.update()


# -------------------- Procesamiento y render de imágenes --------------------

def _process_and_save_image(raw: bytes, filename_hint: str = "image.jpg") -> str:
    """
    Procesa la imagen (auto-orienta, a RGB, redimensiona a máx 1024px, JPEG q=85)
    y la guarda en uploads/pets/<uuid>.jpg. Devuelve **ruta absoluta**.
    """
    from PIL import Image, ImageOps

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    im = Image.open(io.BytesIO(raw))

    # auto-orienta por EXIF
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass

    # a RGB si trae alfa u otros modos
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")

    # redimensiona manteniendo aspecto
    max_side = 1024
    w, h = im.size
    if max(w, h) > max_side:
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

    out_name = f"{uuid.uuid4().hex}.jpg"
    out_path = os.path.join(UPLOADS_DIR, out_name)
    im.save(out_path, format="JPEG", quality=85, optimize=True)
    return out_path


def image_from_photo(
    page: ft.Page,
    photo: str | None,
    *,
    width: int | None = None,
    height: int | None = None,
    fit: ft.ImageFit = ft.ImageFit.COVER,
) -> ft.Image:
    """
    Crea un ft.Image robusto:
      - data:...              -> src
      - /assets/...           -> src
      - ruta local (uploads)  -> Desktop usa src=path, Android/iOS lee bytes -> src_base64
      - vacío/inexistente     -> default por plataforma
    """
    plat = _platform_str(page)
    fallback = _default_photo(page)

    if not photo:
        return ft.Image(src=fallback, width=width, height=height, fit=fit)

    p = str(photo)

    # data URL
    if p.startswith("data:"):
        return ft.Image(src=p, width=width, height=height, fit=fit)

    # ruta servida por Flet
    if p.startswith("/assets/"):
        return ft.Image(src=p, width=width, height=height, fit=fit)

    # archivo local
    if os.path.exists(p):
        if plat in ("windows", "macos", "linux"):  # Desktop
            return ft.Image(src=p, width=width, height=height, fit=fit)
        # Android / iOS -> mejor en base64
        try:
            with open(p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return ft.Image(src_base64=b64, width=width, height=height, fit=fit)
        except Exception:
            pass

    # Fallback
    return ft.Image(src=fallback, width=width, height=height, fit=fit)


# -------------------- Vistas de error --------------------

def _error_view(page: ft.Page, where: str, err: Exception) -> ft.View:
    """Muestra el traceback en pantalla sin crashear la app."""
    tb = traceback.format_exc()
    page_preset(page, f"Error en {where}")
    appbar = ft.AppBar(
        leading=ft.IconButton(icon="arrow_back", on_click=lambda e: page.go("/dashboard")),
        title=ft.Text("Mis Mascotas"),
        bgcolor="#FFFFFF",
    )
    body = ft.Container(
        padding=16,
        content=ft.Column(
            [
                ft.Text("⚠️ Ocurrió un error al cargar la vista.", weight=ft.FontWeight.BOLD),
                ft.Text(str(err), color="#DC2626"),
                ft.Divider(),
                ft.Text("Traceback:", weight=ft.FontWeight.BOLD),
                ft.Container(
                    bgcolor="#F8FAFC",
                    border_radius=8,
                    padding=12,
                    content=ft.Text(tb, selectable=True, size=12),
                ),
                ft.TextButton("Volver al login", on_click=lambda e: page.go("/login")),
            ],
            spacing=10,
        ),
    )
    return ft.View("/pets", appbar=appbar, controls=[body])


# -------------------- Implementación principal --------------------

def _pets_impl(page: ft.Page) -> ft.View:
    db.init_db()

    me = page.session.get("user") or {}
    if not me:
        page.go("/login")
        return ft.View("/login")

    user_id = me.get("id")
    page_preset(page, "Mis Mascotas")

    appbar = ft.AppBar(
        leading=ft.IconButton(icon="arrow_back", on_click=lambda e: page.go("/dashboard")),
        title=ft.Text("Mis Mascotas"),
        bgcolor="#FFFFFF",
    )

    # ------- Estado -------
    list_col = ft.Column(spacing=12, expand=True)

    # Estado para saber si se puede agregar (lo usa View.floating_action_button)
    can_add_state: dict[str, bool] = {"value": False}

    # FilePicker único (lo ponemos en overlay si no estaba)
    file_picker = ft.FilePicker()
    if file_picker not in page.overlay:
        page.overlay.append(file_picker)

    # ------- Popups: QR y Mapa -------

    def _qr_image_for(text: str, size: int = 240) -> ft.Image:
        """
        Genera un QR local (si hay lib 'qrcode'); si no, usa Google Charts.
        Devuelve un ft.Image listo para mostrar.
        """
        try:
            import qrcode
            from PIL import Image
            import io as _io, base64 as _b64

            qr = qrcode.QRCode(
                version=None,  # auto
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(text)
            qr.make(fit=True)
            img: Image.Image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            img = img.resize((size, size))
            buf = _io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            b64 = _b64.b64encode(buf.getvalue()).decode("utf-8")
            return ft.Image(src_base64=b64, width=size, height=size)
        except Exception:
            # Fallback online (puede fallar por red/CSP, pero al menos lo intentamos)
            url = "https://chart.googleapis.com/chart?cht=qr&chs=" + f"{size}x{size}" + "&chl=" + _url.quote(text)
            return ft.Image(src=url, width=size, height=size)

    def open_map(pid: int):
        """
        Muestra un mapa PRECISO usando un WebView con OpenStreetMap embebido
        y un botón para abrir la misma ubicación en Google Maps.
        NO pasa por /static-map ni por tu servidor para el mapa.
        """
        # Coordenadas por defecto (Santiago) si la mascota aún no tiene ubicación
        lat, lng = -33.4489, -70.6693
        try:
            if hasattr(db, "get_pet"):
                info = db.get_pet(pid) or {}
                if info.get("last_lat") is not None and info.get("last_lng") is not None:
                    lat = float(info.get("last_lat"))
                    lng = float(info.get("last_lng"))
        except Exception:
            pass

        # Link a Google Maps con la ubicación real
        gmaps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

        # ---------- URL embebida de OpenStreetMap ----------
        # Calculamos una bbox pequeñita alrededor del punto
        dlat = 0.01
        dlng = 0.01
        left   = lng - dlng
        bottom = lat - dlat
        right  = lng + dlng
        top    = lat + dlat

        bbox = f"{left},{bottom},{right},{top}"
        # Mapa embebido con marcador en la posición de la mascota
        osm_embed_url = (
            "https://www.openstreetmap.org/export/embed.html"
            f"?bbox={_url.quote(bbox)}"
            f"&layer=mapnik"
            f"&marker={lat},{lng}"
        )

        # WebView con el mapa (preciso y cargado directamente desde OSM)
        map_view = ft.WebView(
            url=osm_embed_url,
            width=420,
            height=280,
        )

        dlg = ft.AlertDialog(
            title=ft.Text("Ubicación"),
            content=ft.Column(
                [
                    map_view,
                    ft.Text(
                        f"Lat/Lng: {lat:.6f}, {lng:.6f}",
                        size=11,
                        color=MUTED,
                    ),
                    ft.Row(
                        [
                            ft.FilledButton(
                                "Abrir en Google Maps",
                                icon="open_in_new",
                                on_click=lambda e: page.launch_url(gmaps_link),
                            )
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=10,
                width=440,
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: _close_dialog(page, dlg)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            modal=True,
        )
        _open_dialog(page, dlg)

    # ------- Diálogo: Renombrar -------

    def open_rename_dialog(pet_id: int, current_name: str):
        name_field = ft.TextField(label="Nuevo nombre", value=current_name or "", autofocus=True, width=320)
        msg = ft.Text("", color="#DC2626", visible=False)

        def save(_):
            try:
                new_name = (name_field.value or "").strip()
                db.rename_pet(pet_id, new_name)
                _close_dialog(page, dlg)
                reload_list()
            except Exception as ex:
                msg.value = f"Error: {ex}"
                msg.visible = True
                page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cambiar nombre"),
            content=ft.Column([name_field, msg], spacing=8),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: _close_dialog(page, dlg)),
                ft.ElevatedButton(
                    "Guardar",
                    on_click=save,
                    style=ft.ButtonStyle(bgcolor=PRIMARY, color="#FFFFFF"),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        _open_dialog(page, dlg)

    # ------- UI builders -------

    def _status_chip(status: str) -> ft.Control:
        s = (status or "").lower()
        if s == "active":
            return ft.Container(
                ft.Text("Activa", color="#065f46"),
                bgcolor="#d1fae5",
                padding=ft.padding.symmetric(4, 8),
                border_radius=100,
            )
        if s == "pending":
            return ft.Container(
                ft.Text("Pendiente", color="#92400e"),
                bgcolor="#fef3c7",
                padding=ft.padding.symmetric(4, 8),
                border_radius=100,
            )
        if s == "inactive":
            return ft.Container(
                ft.Text("Inactiva", color="#6b7280"),
                bgcolor="#e5e7eb",
                padding=ft.padding.symmetric(4, 8),
                border_radius=100,
            )
        return ft.Container()

    def _pet_tile(pid: int, name: str, breed: str, photo: str | None, status: str = "active") -> ft.Control:
        hero_img = image_from_photo(page, photo, height=200, fit=ft.ImageFit.COVER)
        hero_box = ft.Container(
            content=hero_img,
            height=200,
            padding=0,
            margin=0,
            alignment=ft.alignment.center,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            border_radius=ft.border_radius.only(top_left=12, top_right=12),
            width=float("inf"),
            expand=True,
        )

        s = (status or "").lower()
        is_active = (s == "active")

        title_row = ft.Row(
            [
                ft.Text(
                    name or "Sin nombre",
                    weight=ft.FontWeight.BOLD,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                ),
                _status_chip(status),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Botones: activos solo si la mascota está activa
        if is_active:
            map_btn = ft.FilledButton("Mapa", icon="location_on", on_click=lambda e, _pid=pid: open_map(_pid))
            qr_btn = ft.FilledButton("QR", icon="qr_code_2", on_click=lambda e, _pid=pid: open_qr(_pid))
            rename_btn = ft.OutlinedButton(
                "Renombrar",
                icon="edit",
                on_click=lambda e, _pid=pid, _n=name: open_rename_dialog(_pid, _n),
            )
        else:
            # Inactiva → botones deshabilitados, sin on_click
            map_btn = ft.FilledButton("Mapa", icon="location_on", disabled=True)
            qr_btn = ft.FilledButton("QR", icon="qr_code_2", disabled=True)
            rename_btn = ft.OutlinedButton("Renombrar", icon="edit", disabled=True)

        actions_row = ft.Row(
            [map_btn, qr_btn, rename_btn],
            alignment=ft.MainAxisAlignment.END,
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        action_bar = ft.Container(
            content=ft.Column([title_row, actions_row], spacing=8),
            bgcolor="#DDEFE5",
            padding=8,
            border_radius=ft.border_radius.only(bottom_left=12, bottom_right=12),
            width=float("inf"),
        )

        return ft.Container(
            content=ft.Column([hero_box, action_bar], spacing=0, width=float("inf"), expand=True),
            bgcolor="#FFFFFF",
            border_radius=12,
            padding=0,
            margin=0,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            width=float("inf"),
            expand=True,
        )

    # ------- Acciones -------

    def open_add_pet(_=None):
        """Crear mascota con foto opcional (flujo con aprobación)."""
        # Verificación previa (respeta límites de plan)
        try:
            ok, reason = db.can_user_add_pet(user_id)
            if not ok:
                sb = ft.SnackBar(ft.Text(reason or "No puedes crear una nueva mascota ahora."))
                page.overlay.append(sb)
                sb.open = True
                page.update()
                return
        except Exception:
            pass

        name  = ft.TextField(label="Nombre", autofocus=True, width=320)
        breed = ft.TextField(label="Raza", width=320)

        selected_path: dict[str, str] = {"value": ""}

        preview_box = ft.Container(
            content=image_from_photo(page, _default_photo(page), height=160, fit=ft.ImageFit.COVER),
            height=160,
            border_radius=12,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        info    = ft.Text("", color=MUTED, size=12)
        msg_ok  = ft.Text("", color="#059669", size=12, visible=False)
        msg_err = ft.Text("", color="#DC2626", size=12, visible=False)

        def set_preview(p: str | None):
            preview_box.content = image_from_photo(page, p or _default_photo(page), height=160, fit=ft.ImageFit.COVER)
            page.update()

        def show_ok(t: str):
            msg_ok.value = t
            msg_ok.visible = True
            msg_err.visible = False
            page.update()

        def show_err(t: str):
            msg_err.value = t
            msg_err.visible = True
            msg_ok.visible = False
            page.update()

        def on_pick_result(ev: ft.FilePickerResultEvent):
            msg_ok.visible = msg_err.visible = False
            page.update()
            if not ev.files:
                return

            f = ev.files[0]

            if getattr(f, "bytes", None):
                try:
                    path = _process_and_save_image(f.bytes, f.name or "image.jpg")
                    selected_path["value"] = path
                    set_preview(path)
                    info.value = os.path.basename(path)
                    show_ok("Imagen preparada ✔")
                    return
                except Exception as ex:
                    show_err(f"Error procesando imagen: {ex}")
                    return

            if getattr(f, "path", None):
                try:
                    with open(f.path, "rb") as fp:
                        raw = fp.read()
                    path = _process_and_save_image(raw, f.name or "image.jpg")
                    selected_path["value"] = path
                    set_preview(path)
                    info.value = os.path.basename(path)
                    show_ok("Imagen preparada ✔")
                    return
                except Exception as ex:
                    show_err(f"Error leyendo/guardando: {ex}")
                    return

            show_err("No se pudo leer el archivo. Prueba nuevamente en esta plataforma.")

        file_picker.on_result = on_pick_result

        def pick_image(_):
            file_picker.pick_files(
                allowed_extensions=["jpg", "jpeg", "png", "webp"],
                allow_multiple=False,
            )

        def save(_):
            try:
                pet_name  = (name.value or "").strip() or "Sin nombre"
                pet_breed = (breed.value or "").strip()
                photo_path = selected_path["value"] or _default_photo(page)

                if hasattr(db, "request_add_pet"):
                    db.request_add_pet(pet_name, pet_breed, photo_path, me["id"])
                else:
                    db.add_pet(pet_name, pet_breed, photo_path, me["id"])

                show_ok("Solicitud enviada ✔ Espera la aprobación del administrador.")
                _close_dialog(page, dlg)
                reload_list()
            except Exception as ex:
                show_err(f"No se pudo guardar: {ex}")

        def cancel(_):
            _close_dialog(page, dlg)

        content = ft.Column(
            [
                ft.Text("Nueva mascota", size=18, weight=ft.FontWeight.BOLD),
                ft.Row(
                    [ft.OutlinedButton("Seleccionar foto", icon="image", on_click=pick_image)],
                    alignment=ft.MainAxisAlignment.START,
                ),
                preview_box,
                info,
                name,
                breed,
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Guardar",
                            on_click=save,
                            style=ft.ButtonStyle(bgcolor=PRIMARY, color="#FFFFFF"),
                        ),
                        ft.TextButton("Cancelar", on_click=cancel),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
                msg_ok,
                msg_err,
            ],
            spacing=10,
            width=360,
        )

        dlg = ft.AlertDialog(content=content, modal=True)
        _open_dialog(page, dlg)

    # ------- Cargar listado -------

    def reload_list():
        list_col.controls.clear()
        try:
            # Preferimos todas con estado; si no existe la función, caemos a activas.
            if hasattr(db, "list_user_all_pets_with_status"):
                rows = db.list_user_all_pets_with_status(user_id)  # (id, name, breed, photo, status)
            else:
                base_rows = db.list_user_pets(user_id, include_pending=True)  # compat
                rows = [(pid, n, b, p, "active") for (pid, n, b, p) in base_rows]
        except Exception as ex:
            list_col.controls.append(ft.Text(f"Error cargando mascotas: {ex}", color="#DC2626"))
            page.update()
            return

        # Consultar posibilidad de crear (para banda y FAB/empty)
        can_add, reason = (True, None)
        try:
            can_add, reason = db.can_user_add_pet(user_id)
        except Exception:
            pass

        # guarda estado para el View inicial
        can_add_state["value"] = bool(can_add)

        # Si NO puede crear, mostramos una banda informativa arriba del listado
        if not can_add and reason:
            list_col.controls.append(
                ft.Container(
                    bgcolor="#FEF3C7",
                    border_radius=8,
                    padding=12,
                    content=ft.Row(
                        [ft.Icon("info"), ft.Text(reason, size=12)],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        if not rows:
            # Estado vacío
            empty_children = [
                ft.Icon("pets", size=48),
                ft.Text("Aún no tienes mascotas", color=MUTED),
            ]
            if can_add:
                empty_children.append(
                    ft.ElevatedButton(
                        "+  Agregar mascota",
                        on_click=open_add_pet,
                        style=ft.ButtonStyle(bgcolor=PRIMARY, color="#FFFFFF"),
                    )
                )
            list_col.controls.append(
                ft.Container(
                    padding=24,
                    alignment=ft.alignment.center,
                    content=ft.Column(
                        empty_children,
                        spacing=8,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )
            # Info de pendientes (si hay API)
            if hasattr(db, "count_pending_for_user"):
                try:
                    pend = db.count_pending_for_user(user_id)
                    if pend > 0:
                        list_col.controls.append(
                            ft.Container(
                                bgcolor="#FFF7ED",
                                border_radius=8,
                                padding=12,
                                content=ft.Row(
                                    [
                                        ft.Icon("hourglass_top"),
                                        ft.Text(
                                            f"Tienes {pend} mascota(s) en revisión. "
                                            f"Serán visibles cuando el administrador las apruebe.",
                                            size=12,
                                        ),
                                    ],
                                    spacing=8,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                            )
                        )
                except Exception:
                    pass

        else:
            for pid, name, breed, photo, status in rows:
                list_col.controls.append(_pet_tile(pid, name, breed, photo, status))

        # Actualizar FAB del View actual (después de que la vista ya exista)
        fab = ft.FloatingActionButton(icon="add", bgcolor=PRIMARY, on_click=open_add_pet) if can_add else None
        if page.views and page.views[-1].route == "/pets":
            page.views[-1].floating_action_button = fab

        page.update()

    # Construye contenido inicial
    reload_list()

    # FAB inicial para la vista (primer render)
    initial_fab = (
        ft.FloatingActionButton(icon="add", bgcolor=PRIMARY, on_click=open_add_pet)
        if can_add_state["value"]
        else None
    )

    return ft.View(
        "/pets",
        appbar=appbar,
        controls=[ft.Container(list_col, padding=12, expand=True)],
        floating_action_button=initial_fab,
    )


# -------------------- Wrapper seguro --------------------

def pets_view(page: ft.Page) -> ft.View:
    """Nunca crashea: si algo falla, muestra el traceback en esta misma vista."""
    try:
        return _pets_impl(page)
    except Exception as e:
        return _error_view(page, "pets_view", e)


def _current_public_base() -> str | None:
    """
    Devuelve la URL pública HTTPS de ngrok si está corriendo (via API 4040).
    Si no hay ngrok, intenta PUBLIC_BASE_URL. Si nada, None.
    """
    # 1) ngrok local API
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as r:
            j = json.loads(r.read().decode("utf-8"))
            for t in j.get("tunnels", []):
                if t.get("proto") == "https" and t.get("public_url"):
                    return t["public_url"].rstrip("/")
    except Exception:
        pass

    # 2) fallback: variable de entorno (por si usas run_public.ps1)
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    return base or None
