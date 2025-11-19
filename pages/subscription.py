# pages/subscription.py
import flet as ft
from services import db
from ui.components import page_preset, card, MUTED, PRIMARY

# Planes disponibles para usuarios (Owner se administra fuera de esta UI)
PLANS_FOR_USER = ["Basic", "Plus"]

# Límites y precios (ajusta precios a lo que quieras mostrar)
PLAN_LIMITS = {"Free": 0, "Basic": 1, "Plus": 5, "Owner": 999999}
PLAN_PRICES = {"Free": 0, "Basic": 2990, "Plus": 4990}  # CLP a modo de ejemplo


def subscription_view(page: ft.Page) -> ft.View:
    db.init_db()
    me = page.session.get("user") or {}
    if not me:
        page.go("/login")
        return ft.View("/login")

    page_preset(page, "Suscripción")
    current_plan = (me.get("plan") or "Free").strip().title()
    plan_lower = current_plan.lower()

    is_free = plan_lower == "free"
    is_basic = plan_lower == "basic"
    is_plus = plan_lower == "plus"

    # ---------- Helpers de feedback ----------
    info = ft.Text("", color="#059669", visible=False)
    err = ft.Text("", color="#DC2626", visible=False)

    def flash_ok(t: str):
        info.value, info.visible = f"✅ {t}", True
        err.visible = False
        page.update()

    def flash_err(t: str):
        err.value, err.visible = f"⚠️ {t}", True
        info.visible = False
        page.update()

    # ---------- Selector de upgrade ----------
    # Reglas:
    #  - Free: puede subir a Basic o Plus
    #  - Basic: puede subir a Plus
    #  - Plus: no muestra upgrade; sólo cancelar
    upgrade_options: list[str] = []
    if is_free:
        upgrade_options = ["Basic", "Plus"]
    elif is_basic:
        upgrade_options = ["Plus"]

    dd = ft.Dropdown(
        label="Selecciona nuevo plan",
        value=(upgrade_options[0] if upgrade_options else None),
        options=[ft.dropdown.Option(p) for p in upgrade_options],
        visible=not is_plus,  # si es Plus no hay upgrade
        width=280,
    )

    def on_upgrade(_):
        target = dd.value
        if not target:
            flash_err("Selecciona un plan para mejorar.")
            return
        ok, url, e = db.create_checkout_order(me["id"], target, amount_cents=0)
        if not ok:
            flash_err(e or "No se pudo crear el checkout.")
            return
        try:
            page.launch_url(url)
            flash_ok("Abrí el checkout en tu navegador. Cuando termines, pulsa “Refrescar”.")
        except Exception:
            flash_ok(f"Abrir manualmente: {url}")

    def on_refresh(_):
        # Refresca el plan desde DB (sin requerir password)
        try:
            plan, _role = db._get_user_plan_role(me["id"])
            plan = (plan or "Free").strip().title()
        except Exception:
            plan = current_plan
        me["plan"] = plan
        page.session.set("user", me)
        flash_ok(f"Plan actual: {plan}")
        # Redibuja la pantalla con el estado actualizado
        page.go("/subscriptions")

    # ---------- Cancelación (Basic y Plus) ----------
    def _open_dialog(d: ft.AlertDialog):
        try:
            page.open(d)
        except Exception:
            page.dialog = d
            d.open = True
            page.update()

    def _close_dialog(d: ft.AlertDialog):
        try:
            page.close(d)
        except Exception:
            d.open = False
            page.update()

    def on_cancel_confirmed(dialog: ft.AlertDialog):
        try:
            ok, msg = db.update_user_plan(me["id"], "Free")
            if ok is False:
                flash_err(msg or "No fue posible cancelar.")
                return
            # Desactiva todas las mascotas al quedar en Free (best-effort)
            try:
                if hasattr(db, "deactivate_all_user_pets"):
                    db.deactivate_all_user_pets(me["id"])
                else:
                    # Si no existe helper, usa enforcement genérico si lo tienes
                    if hasattr(db, "enforce_plan_limits"):
                        db.enforce_plan_limits(me["id"], "Free")
            except Exception:
                pass

            me["plan"] = "Free"
            page.session.set("user", me)
            flash_ok("Suscripción cancelada. Tu plan ahora es Free y todas tus mascotas fueron desactivadas.")
        finally:
            dialog.open = False
            page.update()
            page.go("/dashboard")

    def on_cancel(_):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cancelar suscripción"),
            content=ft.Text(
                "Al cancelar, tu plan pasará a Free y todas tus mascotas quedarán desactivadas.\n"
                "Podrás reactivarlas si vuelves a suscribirte."
            ),
            actions=[
                ft.TextButton("No", on_click=lambda e: _close_dialog(dlg)),
                ft.FilledButton(
                    "Sí, cancelar",
                    icon="cancel",
                    on_click=lambda e: on_cancel_confirmed(dlg),
                    style=ft.ButtonStyle(bgcolor="#DC2626", color="#FFFFFF"),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        _open_dialog(dlg)

    # ---------- Card principal de acciones ----------
    header_text = ft.Text(f"Plan actual: {current_plan}", size=20, weight=ft.FontWeight.BOLD)
    limit_text = ft.Text(f"Límite de mascotas: {PLAN_LIMITS.get(current_plan, 0)}", color=MUTED)

    actions_row: list[ft.Control] = []
    if dd.visible:
        actions_row.append(
            ft.FilledButton(
                "Mejorar plan",
                icon="upgrade",
                on_click=on_upgrade,
                style=ft.ButtonStyle(bgcolor=PRIMARY, color="#FFFFFF"),
            )
        )

    # En Basic y Plus debe permitir cancelar
    if is_basic or is_plus:
        actions_row.append(ft.OutlinedButton("Cancelar suscripción", icon="cancel", on_click=on_cancel))

    # Siempre disponible
    actions_row.append(ft.OutlinedButton("Refrescar", icon="refresh", on_click=on_refresh))

    actions_card = card(
        ft.Column(
            [
                header_text,
                limit_text,
                ft.Divider(),
                dd if dd.visible else ft.Container(),
                ft.Row(actions_row, alignment=ft.MainAxisAlignment.START, spacing=8),
                info,
                err,
            ],
            spacing=12,
        )
    )

    # ---------- Card: Beneficios por plan ----------
    benefits = {
        "Free": [
            "Acceso a la app",
            "0 mascotas activas",
            "QR funcional (página pública) de mascotas existentes (inactivas no visibles en tu listado).",
        ],
        "Basic": [
            "Hasta 1 mascota activa",
            "Página pública con foto, dueño y botón de llamada",
            "Soporte básico",
        ],
        "Plus": [
            "Hasta 5 mascotas activas",
            "Página pública con foto, dueño y botón de llamada",
            "Prioridad en soporte",
        ],
    }

    def plan_badge(name: str) -> ft.Control:
        color = {"Free": "#64748B", "Basic": "#0EA5E9", "Plus": "#22C55E"}.get(name, "#64748B")
        return ft.Container(
            ft.Text(name, color="#FFFFFF", size=12, weight=ft.FontWeight.BOLD),
            bgcolor=color,
            padding=ft.padding.symmetric(6, 10),
            border_radius=100,
        )

    def benefit_list(items: list[str]) -> ft.Control:
        return ft.Column(
            [ft.Row([ft.Text("•"), ft.Text(itm)], spacing=6) for itm in items],
            spacing=4,
        )

    benefits_card = card(
        ft.Column(
            [
                ft.Text("Beneficios por plan", size=18, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.ResponsiveRow(
                    [
                        ft.Container(
                            ft.Column([plan_badge("Free"), benefit_list(benefits["Free"])], spacing=8),
                            col={"xs": 12, "md": 4},
                        ),
                        ft.Container(
                            ft.Column([plan_badge("Basic"), benefit_list(benefits["Basic"])], spacing=8),
                            col={"xs": 12, "md": 4},
                        ),
                        ft.Container(
                            ft.Column([plan_badge("Plus"), benefit_list(benefits["Plus"])], spacing=8),
                            col={"xs": 12, "md": 4},
                        ),
                    ],
                    run_spacing=12,
                ),
            ],
            spacing=12,
        )
    )

    # ---------- Card: Precios y límites ----------
    def price_row(plan_name: str) -> ft.Control:
        price = PLAN_PRICES.get(plan_name, 0)
        limit = PLAN_LIMITS.get(plan_name, 0)
        tag = ft.Text("Actual", color="#16A34A") if plan_name.lower() == plan_lower else ft.Text(" ")
        return ft.Row(
            [
                ft.Container(ft.Text(plan_name, weight=ft.FontWeight.BOLD), width=100),
                ft.Container(ft.Text(f"${price:,d} CLP/mes".replace(",", ".")), width=160),
                ft.Container(ft.Text(f"{limit} mascotas activas"), width=180),
                tag,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    prices_card = card(
        ft.Column(
            [
                ft.Text("Precios y límites", size=18, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                price_row("Free"),
                price_row("Basic"),
                price_row("Plus"),
            ],
            spacing=8,
        )
    )

    # ---------- AppBar ----------
    header = ft.AppBar(
        leading=ft.IconButton(icon="arrow_back", on_click=lambda e: page.go("/dashboard")),
        title=ft.Text("Suscripción"),
        bgcolor="#FFFFFF",
    )

    # ---------- Vista ----------
    return ft.View(
        "/subscriptions",  # usamos la ruta plural (coincide con dashboard.go("/subscriptions"))
        appbar=header,
        controls=[
            ft.Container(actions_card, padding=12, alignment=ft.alignment.top_center),
            ft.Container(
                ft.Column([benefits_card, prices_card], spacing=12),
                padding=ft.padding.only(left=12, right=12, bottom=24),
            ),
        ],
    )
