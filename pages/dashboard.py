# pages/dashboard.py
import os
import asyncio
import json
import urllib.request

import flet as ft
from services import db
from ui.components import asset_image, card, page_preset, MUTED


def _plan_next(current: str) -> str | None:
    """
    Solo planes de usuario: Free -> Basic -> Plus.
    No existe upgrade a Owner desde el dashboard.
    """
    order = ["Free", "Basic", "Plus"]  # <- sin "Owner"
    try:
        i = order.index((current or "Free").strip())
    except ValueError:
        i = 0
    return order[i + 1] if i + 1 < len(order) else None


def dashboard_view(page: ft.Page) -> ft.View:
    # Preset visual y DB
    page_preset(page, "Dashboard")
    try:
        db.init_db()
    except Exception:
        pass

    # -------- Usuario desde sesión --------
    user = page.session.get("user") or {}
    display_name = user.get("name") or user.get("email") or "Usuario"
    plan = user.get("plan", "Basic")
    is_admin = user.get("role") == "admin"

    # Refs reactivas para actualizar luego de editar perfil
    hdr_name_text   = ft.Text(f"Hola, {display_name}", size=16, weight=ft.FontWeight.BOLD)
    hdr_plan_text   = ft.Text(f"Plan: {plan}", size=12, color=MUTED)
    main_title_text = ft.Text(f"¡Bienvenido {display_name}!", size=22, weight=ft.FontWeight.BOLD)

    # ====== helpers de animación ======
    def _ease_out_cubic(t: float) -> float:
        return 1 - (1 - t) ** 3

    async def _animate(duration_ms: int, steps: int, step_fn):
        dt = max(duration_ms / 1000.0, 0.001) / max(steps, 1)
        for k in range(steps + 1):
            p = _ease_out_cubic(k / float(steps))
            step_fn(p)
            page.update()
            await asyncio.sleep(dt)

    # ============== Drawer con animación ==============
    PANEL_W = 260

    def goto_pets(_=None):
        close_drawer()
        page.go("/pets")

    def goto_owner(_=None):
        close_drawer()
        page.go("/owner")

    def do_logout(_=None):
        close_drawer()
        page.session.remove("user")
        page.go("/login")

    def open_profile_popup(_=None):
        close_drawer()

        session_user = page.session.get("user") or {}
        if not session_user:
            page.go("/login")
            return

        name_field  = ft.TextField(label="Nombre",  value=session_user.get("name",""),  width=320)
        phone_field = ft.TextField(label="Teléfono", value=session_user.get("phone",""), width=320)
        msg_err = ft.Text("", color="#DC2626", visible=False)

        def save(_):
            name  = (name_field.value or "").strip()
            phone = (phone_field.value or "").strip()
            if not name and not phone:
                msg_err.value = "Ingresa al menos un dato (nombre o teléfono)."
                msg_err.visible = True
                page.update()
                return

            db.update_user_profile(session_user["id"], name, phone)
            session_user["name"]  = name
            session_user["phone"] = phone
            page.session.set("user", session_user)

            shown = name if name else session_user.get("email","")
            hdr_name_text.value   = f"Hola, {shown}"
            main_title_text.value = f"¡Bienvenido {shown}!"
            page.update()

            try:
                page.close(dlg)
            except Exception:
                dlg.open = False
                page.update()

        def cancel(_):
            try:
                page.close(dlg)
            except Exception:
                dlg.open = False
                page.update()

        content = ft.Column(
            [
                ft.Text("Editar perfil", size=18, weight=ft.FontWeight.BOLD),
                name_field, phone_field,
                ft.Row(
                    [ft.ElevatedButton("Guardar", on_click=save),
                     ft.TextButton("Cancelar", on_click=cancel)],
                    alignment=ft.MainAxisAlignment.END,
                ),
                msg_err,
            ],
            spacing=10, width=360,
        )
        dlg = ft.AlertDialog(content=content, modal=True)
        try:
            page.open(dlg)
        except Exception:
            page.dialog = dlg
            dlg.open = True
            page.update()

    # Overlay que oscurece el fondo (también animado)
    overlay = ft.Container(
        bgcolor="#00000000",  # partimos transparente; visibilidad controlada por animación
        visible=False,
        on_click=lambda e: close_drawer(),
        expand=True,
    )

    # Header del drawer
    drawer_header = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        asset_image(page, "logo_paw.png", width=28, height=28),
                        hdr_name_text,
                    ],
                    spacing=10,
                ),
                hdr_plan_text,
            ],
            spacing=6,
            tight=True,
        ),
        padding=16,
        bgcolor="#E5F4EB",
    )

    # Items del drawer
    top_items = [
        drawer_header,
        ft.Divider(height=1),
        ft.ListTile(leading=ft.Icon("pets"), title=ft.Text("Mis Mascotas"), on_click=goto_pets),
    ]
    bottom_items = [
        ft.ListTile(leading=ft.Icon("edit"), title=ft.Text("Editar perfil"), on_click=open_profile_popup),
        ft.ListTile(leading=ft.Icon("logout"), title=ft.Text("Cerrar sesión", color="#DC2626"), on_click=do_logout),
    ]
    if is_admin:
        bottom_items.insert(
            0,
            ft.ListTile(leading=ft.Icon("admin_panel_settings"), title=ft.Text("Owner"), on_click=goto_owner),
        )

    drawer_panel = ft.Container(
        content=ft.Column(controls=top_items + [ft.Container(expand=True)] + bottom_items, spacing=0),
        width=PANEL_W, bgcolor="#FFFFFF", height=page.height,
    )

    # Drawer contenedor (inicia oculto)
    slide = ft.Container(
        content=drawer_panel,
        width=PANEL_W,
        height=page.height,
        margin=ft.margin.only(left=-PANEL_W),
    )

    def _current_public_base() -> str | None:
        # 1) ngrok local API
        try:
            with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as r:
                j = json.loads(r.read().decode("utf-8"))
                for t in j.get("tunnels", []):
                    if t.get("proto") == "https" and t.get("public_url"):
                        return t["public_url"].rstrip("/")
        except Exception:
            pass
        # 2) fallback a env var (por si usas run_public.ps1)
        base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
        return base or None

    def _set_public_base_env_from_ngrok():
        base = _current_public_base()
        if base:
            os.environ["PUBLIC_BASE_URL"] = base

    def open_drawer():
        overlay.visible = True

        async def run():
            def step(p):
                slide.margin = ft.margin.only(left=int(-PANEL_W * (1 - p)))
                alpha = int(0x59 * p)  # 0..0x59 ~35%
                overlay.bgcolor = f"#000000{alpha:02X}"
            await _animate(220, 10, step)
            slide.margin = ft.margin.only(left=0)
            overlay.bgcolor = "#00000059"
            page.update()
        page.run_task(run)

    def close_drawer():
        async def run():
            def step(p):
                slide.margin = ft.margin.only(left=int(-PANEL_W * p))
                alpha = int(0x59 * (1 - p))
                overlay.bgcolor = f"#000000{alpha:02X}"
            await _animate(180, 8, step)
            slide.margin = ft.margin.only(left=-PANEL_W)
            overlay.bgcolor = "#00000000"
            overlay.visible = False
            page.update()
        page.run_task(run)

    def toggle_drawer(_=None):
        close_drawer() if overlay.visible else open_drawer()

    # -------- Suscripción (AppBar acción arriba a la derecha) --------
    def manage_subscription(_):
        # Admin va al panel Owner
        if is_admin:
            page.go("/owner")
            return

        # (Opcional) refresca PUBLIC_BASE_URL desde ngrok si está corriendo
        try:
            _set_public_base_env_from_ngrok()
        except Exception:
            pass

        # Siempre navega a la pantalla unificada de Suscripciones
        page.go("/subscriptions")

    # AppBar
    header = ft.AppBar(
        leading=ft.IconButton(icon="menu", on_click=toggle_drawer),
        title=ft.Text("Dashboard"),
        bgcolor="#FFFFFF",
        actions=[
            ft.IconButton(
                icon="workspace_premium",
                tooltip="Gestionar suscripción",
                on_click=manage_subscription,
            )
        ],
    )

    # =================== Card principal (bienvenida) ===================
    main_card = card(
        ft.Column(
            [
                asset_image(page, "logo_paw.png", width=80, height=80),
                main_title_text,
                ft.Row([ft.Chip(label=ft.Text(plan))]),
                ft.Text("Este será tu panel principal. Pronto agregaremos secciones.", color=MUTED),
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )
    main_card.width = 560

    # =================== Layout final ===================
    content_column = ft.Column(
        [
            ft.Container(main_card, alignment=ft.alignment.top_center, padding=24),
        ],
        expand=True,
        spacing=0,
    )

    stack = ft.Stack(
        controls=[
            ft.Container(content=content_column, expand=True),
            overlay,   # capa oscura animada
            slide,     # panel lateral animado
        ],
        expand=True,
    )

    return ft.View("/dashboard", appbar=header, controls=[stack])
