import flet as ft
from pages.login import login_view
from pages.register import register_view
from pages.dashboard import dashboard_view
from pages.pets import pets_view
from pages.owner import owner_view
from pages.subscription import subscription_view

def setup_routes(page: ft.Page):
    def route_change(e: ft.RouteChangeEvent):
        page.views.clear()
        try:
            if page.route == "/":
                page.go("/login")
                return

            if page.route == "/login":
                page.views.append(login_view(page))
            elif page.route == "/register":
                page.views.append(register_view(page))
            elif page.route == "/dashboard":
                page.views.append(dashboard_view(page))
            elif page.route == "/pets":
                page.views.append(pets_view(page))
            elif page.route == "/owner":
                page.views.append(owner_view(page))
            elif page.route == "/subscription":
                page.views.append(subscription_view(page))
            else:
                page.views.append(login_view(page))

        except Exception as ex:
            import traceback
            tb = traceback.format_exc()
            page.views.append(
                ft.View(
                    "/error",
                    controls=[
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text("⚠️ Ocurrió un error al cargar la vista.", size=18, weight=ft.FontWeight.BOLD),
                                    ft.Text(str(ex), color="#DC2626"),
                                    ft.Text(tb, size=12, selectable=True, color="#6B7280"),
                                    ft.TextButton("Volver al login", on_click=lambda _: page.go("/login")),
                                ],
                                spacing=10,
                            ),
                            padding=16,
                        )
                    ],
                )
            )
        page.update()

    def view_pop(e: ft.ViewPopEvent):
        page.views.pop()
        page.update()

    page.on_route_change = route_change
    page.on_view_pop = view_pop
