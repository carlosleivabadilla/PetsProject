# pages/subscription.py
import flet as ft
from ui.components import page_preset, card, PRIMARY, MUTED, asset_image
from services import db


def _plan_next(current: str) -> str | None:
    """
    Orden simple de planes de usuario:
    Free -> Basic -> Plus. (Owner solo para admin)
    """
    order = ["Free", "Basic", "Plus"]
    cur = (current or "Free").strip()
    try:
        i = order.index(cur)
    except ValueError:
        i = 0
    return order[i + 1] if i + 1 < len(order) else None


def subscription_view(page: ft.Page) -> ft.View:
    # Init y usuario
    db.init_db()
    user = page.session.get("user") or {}
    if not user:
        page.go("/login")
        return ft.View("/login")

    uid   = user.get("id")
    plan  = (user.get("plan") or "Free").strip()
    email = user.get("email", "")

    page_preset(page, "Suscripción")

    # Mensajes
    ok_msg  = ft.Text("", color="#059669", size=12, visible=False)
    err_msg = ft.Text("", color="#DC2626", size=12, visible=False)

    # Texto de estado
    plan_text = ft.Text(
        f"Tu plan actual: {plan}",
        size=18,
        weight=ft.FontWeight.BOLD,
    )

    # Descripción corta por plan
    def _plan_desc(p: str) -> str:
        p = (p or "Free").strip()
        if p == "Free":
            return "Sin mascotas registradas. Ideal para probar la app."
        if p == "Basic":
            return "Hasta 1 mascota activa. Pensado para un solo compañero."
        if p == "Plus":
            return "Hasta 5 mascotas activas. Para familias con varios peludos."
        if p == "Owner":
            return "Plan administrador sin límites."
        return ""

    desc_text = ft.Text(_plan_desc(plan), color=MUTED, size=12)

    # ---------- Handlers ----------

    def _show_ok(msg: str):
        ok_msg.value = msg
        ok_msg.visible = True
        err_msg.visible = False
        page.update()

    def _show_err(msg: str):
        err_msg.value = msg
        err_msg.visible = True
        ok_msg.visible = False
        page.update()

    def on_upgrade(_):
        """
        Simula un upgrade creando una orden de checkout
        y abriendo la URL devuelta (backend /checkout?...).
        """
        next_plan = _plan_next(plan)
        if not next_plan:
            _show_err("Ya estás en el plan más alto disponible.")
            return

        try:
            ok, checkout_url, err = db.create_checkout_order(uid, next_plan, amount_cents=0)
            if not ok or not checkout_url:
                _show_err(err or "No se pudo crear la orden de actualización.")
                return

            # Abre la URL del checkout (ngrok / backend mock)
            page.launch_url(checkout_url)
            _show_ok(f"Abriendo checkout para actualizar a {next_plan}...")
        except Exception as ex:
            _show_err(f"Error al iniciar upgrade: {ex}")

    def on_cancel_subscription(_):
        """
        Cancela la suscripción → pasa a Free usando change_user_plan.
        Aplica límites (mascotas quedan inactivas si exceden el plan Free).
        """
        try:
            ok, err, stats = db.change_user_plan(uid, "Free")
            if not ok:
                _show_err(err or "No se pudo cancelar la suscripción.")
                return

            # Actualiza usuario en sesión
            user["plan"] = "Free"
            page.session.set("user", user)

            # Actualiza textos en la vista
            new_plan = stats.get("final_plan", "Free")
            plan_text.value = f"Tu plan actual: {new_plan}"
            desc_text.value = _plan_desc(new_plan)

            # Mensaje informativo
            activated   = stats.get("activated", 0)
            deactivated = stats.get("deactivated", 0)
            extra = ""
            if deactivated > 0:
                extra = f" Se desactivaron {deactivated} mascota(s) para ajustarse al plan Free."
            elif activated > 0:
                extra = f" Se reactivaron {activated} mascota(s) según el nuevo plan."

            _show_ok("Suscripción cancelada. Has vuelto al plan Free." + extra)
        except Exception as ex:
            _show_err(f"Error al cancelar la suscripción: {ex}")

    # ---------- UI ----------

    # Botón de upgrade (solo si hay siguiente plan y no es Owner)
    next_plan = _plan_next(plan)
    upgrade_btn: ft.Control | None = None
    if plan != "Owner" and next_plan:
        upgrade_btn = ft.ElevatedButton(
            f"Mejorar a {next_plan}",
            icon="workspace_premium",
            bgcolor=PRIMARY,
            color="#FFFFFF",
            on_click=on_upgrade,
        )

    # Botón de cancelación (solo si no es Free ni Owner)
    cancel_btn: ft.Control | None = None
    if plan in ("Basic", "Plus"):
        cancel_btn = ft.TextButton(
            "Cancelar suscripción (volver a Free)",
            icon="cancel",
            style=ft.ButtonStyle(color="#DC2626"),
            on_click=on_cancel_subscription,
        )

    # Contenido principal
    main_col = ft.Column(
        [
            asset_image(page, "logo_paw.png", width=96, height=96),
            ft.Text("Suscripciones", size=24, weight=ft.FontWeight.BOLD),
            plan_text,
            desc_text,
            ft.Text(f"Cuenta: {email}", size=12, color=MUTED),
            ft.Divider(),
            ft.Text("Opciones de suscripción", size=16, weight=ft.FontWeight.BOLD),
            ft.Column(
                [
                    *( [upgrade_btn] if upgrade_btn else [] ),
                    *( [cancel_btn] if cancel_btn else [] ),
                    ft.TextButton("Volver al Dashboard", on_click=lambda e: page.go("/dashboard")),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ok_msg,
            err_msg,
        ],
        spacing=12,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    content_card = card(main_col)
    content_card.width = 480

    appbar = ft.AppBar(
        title=ft.Text("Suscripciones"),
        bgcolor="#FFFFFF",
        leading=ft.IconButton(icon="arrow_back", on_click=lambda e: page.go("/dashboard")),
    )

    return ft.View(
        "/subscriptions",
        appbar=appbar,
        controls=[
            ft.Container(
                content=content_card,
                alignment=ft.alignment.center,
                expand=True,
            )
        ],
    )
