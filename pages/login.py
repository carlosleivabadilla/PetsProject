import flet as ft
from ui.components import card, page_preset, PRIMARY, MUTED, asset_image
from services import db

ADMIN_EMAIL = "admin@admin.cl"
ADMIN_PASS  = "admin123"

def login_view(page: ft.Page) -> ft.View:
    db.init_db()
    page_preset(page, "PetProject - Login")

    email = ft.TextField(label="Correo", autofocus=True, width=320)
    pwd   = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, width=320)
    msg   = ft.Text("", color="#DC2626", size=12, visible=False)

    def do_login(_):
        msg.visible = False
        try:
            user = db.auth(email.value, pwd.value)
            if user:
                page.session.set("user", user)
                try:
                    page.go("/dashboard")
                except Exception as ex:
                    msg.value = f"Error al abrir dashboard: {ex}"
                    msg.visible = True
                    page.update()
            else:
                msg.value = "Credenciales inválidas"
                msg.visible = True
                page.update()
        except Exception as ex:
            msg.value = f"Error de autenticación: {ex}"
            msg.visible = True
            page.update()

    def fill_admin(_):
        email.value = ADMIN_EMAIL
        pwd.value   = ADMIN_PASS
        msg.visible = False
        page.update()

    btn_login = ft.ElevatedButton(
        "Entrar",
        width=320,
        on_click=do_login,
        style=ft.ButtonStyle(bgcolor=PRIMARY, color="#FFFFFF"),
    )

    content = ft.Column(
        controls=[
            asset_image(page, "logo_paw.png", width=160, height=160),  # logo grande
            ft.Text("Iniciar sesión", size=24, weight=ft.FontWeight.BOLD),
            email, pwd,
            ft.Row([btn_login], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row(
                [
                    ft.TextButton("Crear cuenta", on_click=lambda _: page.go("/register")),
                    ft.TextButton("Autocompletar admin", on_click=fill_admin),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Text("Admin: admin@admin.cl / admin123", size=12, color=MUTED),
            msg,
        ],
        spacing=12,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    container = card(content)
    container.width = 420
    return ft.View("/login", controls=[ft.Container(container, alignment=ft.alignment.center)])
