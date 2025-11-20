# main.py
import flet as ft
from services import db  # <- IMPORTANTE: para refrescar el usuario desde la BD

# --- Helpers de import seguro para evitar NameError / ImportError ---
def _safe_import(view_import, placeholder_title: str):
    try:
        return view_import()
    except Exception:
        def _placeholder_view(page: ft.Page) -> ft.View:
            # Vista mínima para no romper la app si falta un módulo
            body = ft.Column(
                [
                    ft.Text(placeholder_title, size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "Esta vista no está disponible (módulo no encontrado).",
                        color="#6b7280",
                    ),
                    ft.Text(
                        "Revisa imports/rutas en main.py o crea la vista correspondiente.",
                        size=12, color="#94a3b8",
                    ),
                    ft.ElevatedButton("Volver al Dashboard", on_click=lambda e: page.go("/dashboard")),
                ],
                spacing=10,
            )
            return ft.View(
                "/missing",
                appbar=ft.AppBar(title=ft.Text("Aviso"), bgcolor="#FFFFFF"),
                controls=[ft.Container(body, padding=16)],
            )
        return _placeholder_view

# Importa vistas con fallback
dashboard_view    = _safe_import(
    lambda: __import__("pages.dashboard", fromlist=["dashboard_view"]).dashboard_view,
    "Dashboard no disponible",
)
subscription_view = _safe_import(
    lambda: __import__("pages.subscription", fromlist=["subscription_view"]).subscription_view,
    "Suscripciones no disponible",
)
pets_view         = _safe_import(
    lambda: __import__("pages.pets", fromlist=["pets_view"]).pets_view,
    "Mascotas no disponible",
)
owner_view        = _safe_import(
    lambda: __import__("pages.owner", fromlist=["owner_view"]).owner_view,
    "Owner no disponible",
)
login_view        = _safe_import(
    lambda: __import__("pages.login", fromlist=["login_view"]).login_view,
    "Login no disponible",
)
register_view     = _safe_import(
    lambda: __import__("pages.register", fromlist=["register_view"]).register_view,
    "Registro no disponible",
)


def main(page: ft.Page):

    # Guarda la ruta anterior para back navigation si lo usas
    def view_pop(view):
        if len(page.views) > 1:
            page.views.pop()
            page.go(page.views[-1].route)
    page.on_view_pop = view_pop

    def route_change(_):
        page.views.clear()

        # ----- REFRESCAR USUARIO DESDE LA BD -----
        session_user = page.session.get("user")
        user = None
        if session_user and session_user.get("id"):
            try:
                fresh = db.get_user_by_id(session_user["id"])
            except Exception:
                fresh = None

            if fresh:
                # Actualiza sesión con los datos recién sacados de la BD
                page.session.set("user", fresh)
                user = fresh
            else:
                user = session_user
        else:
            user = None
        # -----------------------------------------

        # Alias: singular -> plural
        if page.route == "/subscription":
            page.go("/subscriptions")
            return

        # Rutas privadas que requieren sesión
        private_routes = {"/dashboard", "/pets", "/subscriptions", "/owner"}

        # Guardia: si intenta entrar a privadas sin sesión → login
        if page.route in private_routes and not user:
            page.views.append(login_view(page))
            page.update()
            return

        # Router
        r = page.route
        if r == "/" or r == "/dashboard":
            page.views.append(dashboard_view(page))
        elif r == "/pets":
            page.views.append(pets_view(page))
        elif r == "/subscriptions":             # ← plural
            page.views.append(subscription_view(page))
        elif r == "/owner":
            # Solo admin
            if user and user.get("role") == "admin":
                page.views.append(owner_view(page))
            else:
                page.views.append(dashboard_view(page))
        elif r == "/login":
            page.views.append(login_view(page))
        elif r == "/register":
            page.views.append(register_view(page))
        else:
            # Ruta desconocida: si hay sesión, manda a dashboard; si no, a login
            page.views.append(dashboard_view(page) if user else login_view(page))

        page.update()

    page.on_route_change = route_change

    # Arranque inicial: si no hay ruta, ve al dashboard o login según sesión
    if not page.route or page.route == "/":
        page.go("/dashboard" if page.session.get("user") else "/login")
    else:
        # Respeta ruta actual (útil en hot-reload)
        page.go(page.route)


if __name__ == "__main__":
    ft.app(target=main)
