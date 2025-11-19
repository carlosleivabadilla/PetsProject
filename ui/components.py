import os
import base64
import flet as ft

# Paleta base (hex)
PRIMARY  = "#1F7A46"   # verde marca
BG       = "#EAF6EF"   # fondo verdoso claro
SURFACE  = "#FFFFFF"   # tarjetas blancas
MUTED    = "#6B7280"   # texto secundario
SUCCESS  = "#CDE8D5"   # verde suave para fondos de acciones

# ----------------- Helpers de assets -----------------

def asset_path(path: str) -> str:
    """Devuelve /assets/... para Web/Desktop."""
    return f"/assets/{path.lstrip('/')}"

def _assets_fs_path(filename: str) -> str:
    """Ruta real en disco dentro de ./assets."""
    return os.path.join("assets", filename)

def _page_platform(page: ft.Page) -> str:
    """
    Devuelve el nombre de plataforma en minúsculas sin romper si es PagePlatform.
    """
    p = getattr(page, "platform", None)
    if p is None:
        return ""
    v = getattr(p, "value", None)
    if isinstance(v, str):
        return v.lower()
    # fallback: str(enum) -> "PagePlatform.WEB" o "web"
    return str(p).lower()

# --- Utils robustos para logos (se mantienen por compatibilidad) ---
def ensure_png_from_svg(svg_name: str) -> str:
    """
    Si existe assets/<svg_name> y NO existe assets/<mismo nombre>.png,
    intenta convertir con cairosvg. Devuelve el path web '/assets/xxx.png'.
    (No es obligatorio usarlo: ahora preferimos PNG directo.)
    """
    svg_fs = _assets_fs_path(svg_name)
    base, _ = os.path.splitext(svg_name)
    png_name = f"{base}.png"
    png_fs = _assets_fs_path(png_name)

    if not os.path.exists(svg_fs):
        # no hay svg; devolvemos el png igual por si ya existe
        return asset_path(png_name)

    if not os.path.exists(png_fs):
        try:
            import cairosvg  # type: ignore
            os.makedirs(os.path.dirname(png_fs), exist_ok=True)
            cairosvg.svg2png(url=svg_fs, write_to=png_fs, output_width=256, output_height=256)
        except Exception:
            pass

    return asset_path(png_name)


def logo_image_from_svg(svg_name: str, *, width: int, height: int) -> ft.Image:
    """
    Garantiza un PNG en assets a partir del SVG y lo muestra.
    Mantendida por compatibilidad; ahora recomendamos usar logo PNG directo.
    """
    png_web = ensure_png_from_svg(svg_name)  # '/assets/logo_paw.png'
    return ft.Image(src=png_web, width=width, height=height, fit=ft.ImageFit.CONTAIN)

def vector_img(page: ft.Page, filename: str, *, width: int = 28, height: int = 28) -> ft.Control:
    """
    Versión simple y robusta:
      - Si pasan .svg, usa el .png homónimo.
      - Si ya es bitmap (.png/.jpg/.jpeg/.webp), úsalo tal cual.
      - Nunca intenta SVG directo ni base64.
    """
    fn = filename.strip()
    lower = fn.lower()

    if lower.endswith(".svg"):
        fn = os.path.splitext(fn)[0] + ".png"

    return ft.Image(src=asset_path(fn), width=width, height=height, fit=ft.ImageFit.CONTAIN)

def asset_image(page: ft.Page, filename: str, *, width: int, height: int, fit=ft.ImageFit.CONTAIN) -> ft.Image:
    """
    Imagen de assets robusta:
      - Web: usa /assets/filename
      - Desktop/Android/iOS: usa ruta de archivo ./assets/filename si existe (mejor para móviles)
      - Fallback: lee bytes -> base64
    """
    fn = filename.lstrip("/")

    # si te pasan un svg, fuerza el .png homónimo
    if fn.lower().endswith(".svg"):
        fn = os.path.splitext(fn)[0] + ".png"

    web_src = asset_path(fn)          # "/assets/logo_paw.png"
    fs_path = _assets_fs_path(fn)     # "assets/logo_paw.png"
    plat = _page_platform(page)

    if plat == "web":
        return ft.Image(src=web_src, width=width, height=height, fit=fit)

    # Desktop / móviles: preferimos ruta de archivo si existe
    if os.path.exists(fs_path):
        return ft.Image(src=fs_path, width=width, height=height, fit=fit)

    # Fallback: intenta base64 por si el runtime no sirve el path
    try:
        with open(fs_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return ft.Image(src_base64=b64, width=width, height=height, fit=fit)
    except Exception:
        # último recurso: intenta el path web
        return ft.Image(src=web_src, width=width, height=height, fit=fit)

# ----------------- Presets y UI -----------------

def page_preset(page: ft.Page, title: str):
    page.title = title
    page.padding = 16
    page.bgcolor = BG
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.START

def card(content: ft.Control) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=SURFACE,
        border_radius=16,
        padding=16,
    )
