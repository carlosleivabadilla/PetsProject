import os
import flet as ft
from ui.components import card, page_preset, MUTED
from services import db

PLANS = ["Basic", "Pro", "Owner"]

DEFAULT_PET = "/assets/dog.jpg"
DEFAULT_PET_WEB = "/assets/dog.jpg"
DEFAULT_PET_FS = "assets/dog.jpg"


# -------- Helpers de plataforma / imagen --------
def _platform_str(page: ft.Page) -> str:
    p = getattr(page, "platform", None)
    if p is None:
        return ""
    v = getattr(p, "value", None)
    if isinstance(v, str):
        return v.lower()
    return str(p).lower()


def _default_pet(page: ft.Page) -> str:
    return (
        DEFAULT_PET_WEB
        if _platform_str(page) == "web"
        else (DEFAULT_PET_FS if os.path.exists(DEFAULT_PET_FS) else DEFAULT_PET_WEB)
    )


def _img_from(photo: str | None, *, w: int = 38, h: int = 38) -> ft.Image:
    """Miniatura robusta para fotos de mascota."""
    if not photo:
        return ft.Image(src=DEFAULT_PET, width=w, height=h, fit=ft.ImageFit.COVER)

    # data URL -> Flet acepta pasarla en src directamente
    if isinstance(photo, str) and photo.startswith("data:"):
        return ft.Image(src=photo, width=w, height=h, fit=ft.ImageFit.COVER)

    # assets servidos por Flet o URL http(s)
    if photo.startswith("/assets/") or photo.startswith("http://") or photo.startswith("https://"):
        return ft.Image(src=photo, width=w, height=h, fit=ft.ImageFit.COVER)

    # ruta local existente
    if os.path.exists(photo):
        return ft.Image(src=photo, width=w, height=h, fit=ft.ImageFit.COVER)

    # fallback
    return ft.Image(src=DEFAULT_PET, width=w, height=h, fit=ft.ImageFit.COVER)


# -------- Vista Owner --------
def owner_view(page: ft.Page) -> ft.View:
    db.init_db()
    me = page.session.get("user") or {}
    if me.get("role") != "admin":
        page.go("/dashboard")
        return ft.View("/dashboard")

    page_preset(page, "Owner")

    banner_err = ft.Text("", color="#DC2626", visible=False)
    banner_ok = ft.Text("", color="#059669", visible=False)

    def flash_ok(msg: str):
        banner_ok.value = f"✅ {msg}"
        banner_ok.visible = True
        banner_err.visible = False
        page.update()

    def flash_err(msg: str):
        banner_err.value = f"⚠️ {msg}"
        banner_err.visible = True
        banner_ok.visible = False
        page.update()

    # =============== SECCIÓN: SOLICITUDES PENDIENTES ===============
    pending_list = ft.Column(spacing=8)

    def reload_pending():
        pending_list.controls.clear()
        rows = db.list_pending_pets()  # [(id, name, breed, photo, user_id, email, user_name, requested_at)]
        count = len(rows)

        header = ft.Row(
            [ft.Text(f"Solicitudes pendientes ({count})", size=18, weight=ft.FontWeight.BOLD)],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        pending_list.controls.append(header)

        if not rows:
            pending_list.controls.append(
                ft.Container(
                    padding=16,
                    bgcolor="#F3F4F6",
                    border_radius=12,
                    content=ft.Row(
                        [ft.Icon("inbox", size=20), ft.Text("No hay solicitudes en espera.", color=MUTED)],
                        spacing=8,
                    ),
                )
            )
        else:
            for pid, name, breed, photo, uid, email, uname, reqat in rows:

                def do_approve(_=None, _pid=pid):
                    db.approve_pet(_pid, me["id"])
                    flash_ok(f"Solicitud aprobada: {name or 'Sin nombre'}")
                    reload_pending()

                def do_reject(_=None, _pid=pid):
                    db.reject_pet(_pid, me["id"])
                    flash_ok(f"Solicitud rechazada: {name or 'Sin nombre'}")
                    reload_pending()

                pending_list.controls.append(
                    ft.Container(
                        bgcolor="#FFFFFF",
                        border_radius=12,
                        padding=10,
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=_img_from(photo, w=56, h=56),  # <-- SIN 'page'
                                    width=56,
                                    height=56,
                                    border_radius=8,
                                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(name or "Sin nombre", weight=ft.FontWeight.BOLD),
                                        ft.Text(breed or "—", color=MUTED, size=12),
                                        ft.Text(f"Solicitante: {uname or email or '—'}", color=MUTED, size=12),
                                        ft.Text(f"Solicitado: {reqat or '—'}", color=MUTED, size=12),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.Row(
                                    [
                                        ft.FilledButton(
                                            "Aprobar",
                                            icon="check",
                                            on_click=do_approve,
                                            style=ft.ButtonStyle(bgcolor="#16A34A", color="#FFFFFF"),
                                        ),
                                        ft.OutlinedButton("Rechazar", icon="close", on_click=do_reject),
                                    ],
                                    spacing=8,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    )
                )
        page.update()

    # =============== SECCIÓN: GESTIÓN DE USUARIOS ===============
    try:
        orphans = db.count_orphan_pets()
    except Exception:
        orphans = 0

    warning_orphans = ft.Container(
        content=ft.Row(
            [
                ft.Icon(name="info", size=18),
                ft.Text(
                    f"Hay {orphans} mascota(s) sin dueño por cambios de esquema. "
                    "Puedes asignarlas a un usuario con el botón 'adoptar'."
                ),
            ],
            spacing=8,
        ),
        padding=10,
        border_radius=12,
        bgcolor="#FEF3C7",
        visible=(orphans > 0),
    )

    users_list = ft.ListView(spacing=10, expand=1, padding=0)

    def confirm(title: str, message: str, on_yes):
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions_alignment=ft.MainAxisAlignment.END,
            modal=True,
        )

        def on_cancel(_):
            dlg.open = False
            page.update()

        def on_yes_click(_):
            try:
                on_yes()
            finally:
                try:
                    page.close(dlg)
                except Exception:
                    dlg.open = False
                    page.update()

        dlg.actions = [
            ft.TextButton("Cancelar", on_click=on_cancel),
            ft.ElevatedButton("Sí", on_click=on_yes_click),
        ]

        try:
            page.open(dlg)
        except Exception:
            page.dialog = dlg
            dlg.open = True
            page.update()

    def render_user_card(uid, email, name, phone, plan, role):
        dd_plan = ft.Dropdown(
            value=plan,
            options=[ft.dropdown.Option(p) for p in PLANS],
            disabled=(role == "admin"),
        )

        def on_save_plan_click(_):
            ok, msg = db.update_user_plan(uid, dd_plan.value)
            flash_ok(f"Plan de {email} actualizado a {dd_plan.value}") if ok else flash_err(
                msg or "No se pudo actualizar"
            )

        def open_pets(_):
            nonlocal_dialog = {"dlg": None}

            def close_dlg():
                dlg = nonlocal_dialog["dlg"]
                if not dlg:
                    return
                try:
                    page.close(dlg)
                except Exception:
                    dlg.open = False
                    page.update()

            def make_delete_one_handler(pid: int, pname: str):
                def handler(_):
                    def do_delete():
                        db.delete_pet(pid)
                        flash_ok(f"Mascota '{pname}' eliminada")
                        close_dlg()
                        open_pets(None)
                    confirm("Eliminar mascota", f"¿Eliminar '{pname}'?", do_delete)

                return handler

            def on_delete_all_click(_):
                def do_delete_all():
                    db.delete_user_pets(uid)
                    flash_ok(f"Mascotas de {email} eliminadas")
                    close_dlg()
                    open_pets(None)

                confirm("Eliminar todas", f"¿Eliminar TODAS las mascotas de {email}?", do_delete_all)

            items = []
            pets = db.list_user_all_pets_with_status(uid)  # incluye estado
            if not pets:
                items.append(ft.Text("Este usuario no tiene mascotas.", color=MUTED))
            else:
                for pid, pname, pbreed, pphoto, pstatus in pets:
                    badge = ft.Chip(label=ft.Text(pstatus or "unknown"))
                    items.append(
                        ft.ListTile(
                            leading=_img_from(pphoto, w=38, h=38),
                            title=ft.Row(
                                [ft.Text(pname or "Sin nombre"), badge],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            subtitle=ft.Text(pbreed or ""),
                            trailing=ft.IconButton(
                                icon="delete", tooltip="Eliminar", on_click=make_delete_one_handler(pid, pname or "")
                            ),
                        )
                    )

            dlg = ft.AlertDialog(
                title=ft.Text(f"Mascotas de {email}"),
                content=ft.Container(
                    ft.Column(
                        items
                        + [
                            ft.Divider(),
                            ft.Row(
                                [ft.FilledButton("Eliminar todas", icon="delete_forever", on_click=on_delete_all_click)],
                                alignment=ft.MainAxisAlignment.END,
                            ),
                        ],
                        spacing=6,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    width=420,
                    height=360,
                ),
                actions=[ft.TextButton("Cerrar", on_click=lambda e: close_dlg())],
                actions_alignment=ft.MainAxisAlignment.END,
                modal=True,
            )
            nonlocal_dialog["dlg"] = dlg

            try:
                page.open(dlg)
            except Exception:
                page.dialog = dlg
                dlg.open = True
                page.update()

        def on_delete_account_click(_):
            if role == "admin":
                return

            def do_delete():
                ok, msg = db.delete_user_and_pets(uid)
                if ok:
                    flash_ok(f"Cuenta de {email} eliminada")
                    load_users()
                else:
                    flash_err(msg or "No se pudo eliminar")

            confirm(
                "Eliminar cuenta",
                f"¿Eliminar la CUENTA de {email} y TODAS sus mascotas? Esta acción no se puede deshacer.",
                do_delete,
            )

        def on_adopt_orphans_click(_):
            def do_adopt():
                n = db.attach_orphan_pets_to_user(uid)
                flash_ok(f"Se asignaron {n} mascota(s) huérfanas a {email}")
                load_users()

            confirm("Asignar mascotas huérfanas", f"¿Asignar TODAS las mascotas sin dueño a {email}?", do_adopt)

        actions = [
            ft.Text("Plan:", weight=ft.FontWeight.BOLD),
            dd_plan,
            ft.IconButton(
                icon="save", tooltip="Guardar plan", on_click=on_save_plan_click, disabled=(role == "admin")
            ),
            ft.IconButton(icon="pets", tooltip="Ver mascotas", on_click=open_pets),
        ]
        if orphans > 0:
            actions.insert(
                0,
                ft.IconButton(
                    icon="how_to_reg", tooltip="Adoptar huérfanas", on_click=on_adopt_orphans_click
                ),
            )
        actions.append(
            ft.IconButton(
                icon="person_remove",
                tooltip="Eliminar cuenta",
                on_click=on_delete_account_click,
                disabled=(role == "admin"),
            )
        )

        return card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(email, weight=ft.FontWeight.BOLD),
                                    ft.Text(name or "Sin nombre", color=MUTED, size=12),
                                    ft.Text(phone or "—", color=MUTED, size=12),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Chip(label=ft.Text(role)),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(actions, spacing=8),
                ],
                spacing=10,
            )
        )

    def load_users():
        users_list.controls.clear()
        try:
            rows = db.list_users()
        except Exception as e:
            flash_err(f"Error cargando usuarios: {e}")
            page.update()
            return

        if not rows:
            users_list.controls.append(ft.Text("No hay usuarios.", color=MUTED))
        else:
            for uid, email, name, phone, plan, role in rows:
                users_list.controls.append(render_user_card(uid, email, name, phone, plan, role))
        page.update()

    # Render
    reload_pending()
    load_users()

    content = ft.Column(
        [
            card(
                ft.Column(
                    [
                        ft.Text("Solicitudes de mascotas", size=20, weight=ft.FontWeight.BOLD),
                        pending_list,
                    ],
                    spacing=12,
                )
            ),
            card(
                ft.Column(
                    [
                        ft.Text("Gestión de cuentas", size=20, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "Admin primero. Cambia planes, ver/eliminar mascotas y eliminar cuentas (excepto admin).",
                            color=MUTED,
                        ),
                        warning_orphans,
                        banner_err,
                        banner_ok,
                        users_list,
                    ],
                    spacing=12,
                )
            ),
        ],
        spacing=12,
    )

    header = ft.AppBar(
        leading=ft.IconButton(icon="arrow_back", on_click=lambda e: page.go("/dashboard")),
        title=ft.Text("Owner"),
        bgcolor="#FFFFFF",
    )

    return ft.View(
        "/owner",
        appbar=header,
        controls=[ft.Container(content, alignment=ft.alignment.top_center, padding=12)],
    )
