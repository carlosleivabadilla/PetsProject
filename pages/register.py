import flet as ft
from ui.components import card, page_preset, PRIMARY, MUTED, asset_image
from services import db

def register_view(page: ft.Page) -> ft.View:
    db.init_db()
    page_preset(page, "Crear cuenta")

    name  = ft.TextField(label="Nombre", width=320, autofocus=True)
    phone = ft.TextField(label="Teléfono", width=320)
    email = ft.TextField(label="Correo (requerido)", width=320)
    pwd1  = ft.TextField(label="Contraseña", password=True, can_reveal_password=True, width=320)
    pwd2  = ft.TextField(label="Repite la contraseña", password=True, can_reveal_password=True, width=320)

    ok  = ft.Text("", color="#059669", size=12, visible=False)
    err = ft.Text("", color="#DC2626", size=12, visible=False)

    def valid_password(p: str) -> bool:
        if p is None:
            return False
        p = p.strip()
        return len(p) >= 6 and any(ch.isupper() for ch in p)

    def do_register(_):
        ok.visible = False
        err.visible = False

        if not email.value or not pwd1.value:
            err.value = "Correo y contraseña son obligatorios"
            err.visible = True
            page.update()
            return

        if pwd1.value != pwd2.value:
            err.value = "Las contraseñas no coinciden"
            err.visible = True
            page.update()
            return

        if not valid_password(pwd1.value):
            err.value = "La contraseña debe tener al menos 6 caracteres y una letra mayúscula"
            err.visible = True
            page.update()
            return

        success, error = db.register(
            email.value,
            pwd1.value,
            name.value or "",
            phone.value or ""
        )

        if success:
            ok.value = "✅ Cuenta creada con plan Basic."
            ok.visible = True
        else:
            err.value = f"Error: {error}"
            err.visible = True

        page.update()

    btn = ft.ElevatedButton(
        "Crear cuenta",
        width=320,
        on_click=do_register,
        style=ft.ButtonStyle(bgcolor=PRIMARY, color="#FFFFFF"),
    )

    content = ft.Column(
        controls=[
            asset_image(page, "logo_paw.png", width=120, height=120),  # logo en register
            ft.Text("Registro", size=24, weight=ft.FontWeight.BOLD),
            name, phone, email, pwd1, pwd2,
            ft.Row([btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.TextButton("Iniciar sesión", on_click=lambda _: page.go("/login")),
            ok, err,
        ],
        spacing=12,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    card_container = card(content)
    card_container.width = 420

    # ⬇️ CENTRADO VERTICAL Y HORIZONTAL
    root = ft.Container(
        content=card_container,
        expand=True,
        alignment=ft.alignment.center,
    )

    return ft.View("/register", controls=[root])
