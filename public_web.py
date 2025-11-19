# public_web.py
import os, mimetypes, html, base64, json
from typing import Optional

from fastapi import FastAPI, HTTPException, Response, Request, Header
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from services import db

DEFAULT_IMG_FS  = "assets/dog.jpg"
LOGO_PATH_FS    = "assets/logo_paw.png"

app = FastAPI(title="PetProject Public")

# ---------- utils (idénticas a tu versión previa) ----------

def _read_file_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _abs_url(request: Request, path: str) -> str:
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    base = str(request.base_url).rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"

def _file_to_data_url(path: str) -> str | None:
    raw = _read_file_bytes(path)
    if not raw:
        return None
    mime = mimetypes.guess_type(path)[0] or "image/png"
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _is_stripe_enabled() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY"))

# ---------- imagen pública ----------

@app.get("/img/{pet_id}")
def image_for_pet(pet_id: int):
    info = db.get_pet(pet_id)
    if not info:
        raise HTTPException(404, "Pet not found")

    raw = _read_file_bytes(info.get("photo"))
    ctype = mimetypes.guess_type(info.get("photo") or "")[0] if raw else None
    if not raw:
        raw = _read_file_bytes(DEFAULT_IMG_FS)
        ctype = "image/jpeg" if raw else None
    if not raw or not ctype:
        raise HTTPException(404, "Image not found")

    return Response(content=raw, media_type=ctype)

# ---------- página pública del QR ----------

@app.get("/p", response_class=HTMLResponse)
def public_card(t: str | None = None, request: Request = None):
    if not t:
        raise HTTPException(400, "Missing token")
    info = db.get_public_pet_info_by_token(t)
    if not info:
        raise HTTPException(404, "Pet not found")

    pet_id     = int(info["pet_id"])
    pet_name   = html.escape(info["pet_name"] or "Sin nombre")
    owner_name = html.escape(info["owner_name"] or "Dueño no disponible")
    phone      = (info["owner_phone"] or "").strip()

    img_url = _abs_url(request, f"/img/{pet_id}")
    call_href = f"tel:{phone}" if phone else "#"
    call_disabled_class = "disabled" if not phone else ""

    logo_data_url = _file_to_data_url(LOGO_PATH_FS) or ""
    bg_node = (
        f'<div class="logo" style="background-image:url({logo_data_url});"></div>'
        if logo_data_url
        else """<div class="paw">
  <svg viewBox="0 0 512 512" role="img" aria-label="Fondo decorativo">
    <path fill="#94a3b8" d="M256 288c-53 0-96 43-96 96s43 96 96 96 96-43 96-96-43-96-96-96Zm-144-64c-35 0-64-29-64-64s29-64 64-64 64 29 64 64-29 64-64 64Zm288 0c-35 0-64-29-64-64s29-64 64-64 64 29 64 64-29 64-64 64ZM176 256c-44 0-80-36-80-80s36-80 80-80 80 36 80 80-36 80-80 80Zm160 0c-44 0-80-36-80-80s36-80 80-80 80 36 80 80-36 80-80 80Z"/>
  </svg>
</div>"""
    )

    html_doc = f"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{pet_name} — PetProject</title>
<style>
  :root {{
    --bg: #f1f5f9; --fg: #111827; --muted: #6b7280; --primary: #2563eb;
    --card-w: 820px;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, sans-serif;
    min-height: 100vh; display: grid; place-items: center; overflow: hidden;
  }}
  .stage {{ position: relative; width: 100%; height: 100vh; display: grid; place-items: center; padding: 16px; }}
  .bg {{ position: absolute; inset: 0; overflow: hidden; pointer-events: none; display: grid; place-items: center; }}
  .bg .logo {{
    width: 68vmin; height: 68vmin; filter: blur(26px); opacity: .12;
    background-size: contain; background-repeat: no-repeat; background-position: center;
  }}
  .bg .paw {{ width: 65vmin; height: 65vmin; opacity: .12; filter: blur(24px); }}
  .bg svg {{ width: 100%; height: 100%; }}

  .card {{
    position: relative; z-index: 1;
    width: min(100%, var(--card-w)); background: #fff; border-radius: 16px; overflow: clip;
    box-shadow: 0 10px 30px rgba(0,0,0,.12);
  }}
  .content {{
    display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center; padding: 16px;
  }}
  .left {{ display: grid; grid-template-columns: 160px 1fr; gap: 16px; align-items: center; }}
  .photo {{ width: 160px; height: 160px; border-radius: 12px; overflow: hidden; background:#e5e7eb; }}
  .photo img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .title {{ margin: 0 0 4px; font-size: 22px; font-weight: 700; }}
  .muted {{ margin: 0; color: var(--muted); font-size: 14px; }}
  .right {{ display: flex; align-items: center; justify-content: flex-end; min-width: 180px; }}
  .btn {{
    display: inline-flex; align-items: center; gap: 10px;
    background: var(--primary); color: #fff; text-decoration: none;
    padding: 12px 16px; border-radius: 12px; font-weight: 600;
    transition: transform .03s ease-in-out, opacity .2s; white-space: nowrap;
  }}
  .btn:active {{ transform: scale(.98); }}
  .btn.disabled {{ pointer-events: none; opacity: .55; }}

  @media (max-width: 720px) {{
    .content {{ grid-template-columns: 1fr; }}
    .right {{ justify-content: stretch; }}
    .left {{ grid-template-columns: 1fr; }}
    .photo {{ width: 100%; height: auto; aspect-ratio: 1/1; }}
  }}
</style>

<div class="stage">
  <div class="bg" aria-hidden="true">
    {bg_node}
  </div>

  <article class="card" role="region" aria-label="Ficha de mascota">
    <div class="content">
      <div class="left">
        <div class="photo"><img src="{img_url}" alt="Foto de {pet_name}"></div>
        <div class="text">
          <h1 class="title">{pet_name}</h1>
          <p class="muted">Dueño: {owner_name}</p>
        </div>
      </div>
      <div class="right">
        <a class="btn {call_disabled_class}" href="{call_href}" aria-disabled="{str(not bool(phone)).lower()}">
          <span aria-hidden="true">📞</span><span>Llamar al dueño</span>
        </a>
      </div>
    </div>
  </article>
</div>
</html>
"""
    return HTMLResponse(html_doc)

# ---------- Checkout / gestión de suscripción ----------

PRICES = {"Basic": 2990, "Plus": 4990}
FEATURES = {
    "Free":  ["Sin mascotas", "Soporte básico"],
    "Basic": ["1 mascota", "QR público", "Actualizaciones básicas"],
    "Plus":  ["Hasta 5 mascotas", "QR público", "Mapas y ubicación", "Soporte prioritario"],
    "Owner": ["Ilimitado", "Herramientas de administración"],
}

def _render_features(plan: str) -> str:
    return "".join(f"<li>✅ {html.escape(x)}</li>" for x in FEATURES.get(plan, []))

def _amount_for_plan(plan: str) -> int:
    return int(PRICES.get(plan, 0))

def _get_purchase(ext_id: str):
    with db._conn() as conn:
        row = conn.execute(
            "SELECT id, user_id, target_plan, status, amount_cents, created_at FROM purchases WHERE external_id=?",
            (ext_id,)
        ).fetchone()
        if not row:
            return None
        keys = ["id","user_id","target_plan","status","amount_cents","created_at"]
        return dict(zip(keys, row))

def _get_user_plan(uid: int) -> str:
    with db._conn() as conn:
        row = conn.execute("SELECT plan FROM users WHERE id=?", (uid,)).fetchone()
        return (row[0] if row else "Free")

def _rank():
    return ["Free","Basic","Plus","Owner"]

def _checkout_card_html(plan_to_buy: str, amount: int, tkn: str, request: Request, current_plan: str) -> str:
    pay_url    = _abs_url(request, f"/checkout/pay?t={tkn}")
    cancel_url = _abs_url(request, f"/checkout/cancel?t={tkn}")
    stripe_url = _abs_url(request, f"/checkout/create-stripe?t={tkn}")

    # acciones de downgrade/cancel
    to_basic = _abs_url(request, f"/checkout/downgrade?t={tkn}&to=Basic")
    to_free  = _abs_url(request, f"/checkout/downgrade?t={tkn}&to=Free")

    stripe_btn = (
        f'<a class="btn stripe" href="{stripe_url}">Pagar con Stripe</a>'
        if _is_stripe_enabled() else
        '<a class="btn stripe disabled" href="#" aria-disabled="true" title="Stripe no configurado">Pagar con Stripe</a>'
    )

    # UI
    return f"""
<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Suscripción — PetProject</title>
<style>
  :root {{
    --bg:#f4f6f9; --fg:#111827; --muted:#6b7280; --ok:#22c55e; --primary:#2563eb; --warn:#ef4444;
  }}
  body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,sans-serif;background:var(--bg);margin:0;padding:24px;color:var(--fg)}}
  .wrap{{max-width:980px;margin:0 auto}}
  h1{{margin:0 0 6px}}
  .muted{{color:var(--muted)}}
  .grid{{display:grid;grid-template-columns:1.5fr 1fr;gap:16px}}
  .card{{background:#fff;border-radius:16px;box-shadow:0 8px 24px rgba(0,0,0,.08);padding:20px}}
  .plan-name{{font-weight:800;font-size:22px;margin:0 0 6px}}
  .price{{font-size:28px;font-weight:800;margin:0}}
  .per{{color:var(--muted);font-size:14px}}
  ul{{margin:12px 0 0 18px}}
  .actions{{display:flex;gap:10px;justify-content:flex-end;margin-top:16px;flex-wrap:wrap}}
  .btn{{padding:12px 16px;border-radius:12px;text-decoration:none;display:inline-flex;align-items:center;gap:8px;font-weight:600}}
  .pay{{background:var(--ok);color:#fff}}
  .stripe{{background:#635bff;color:#fff}}
  .cancel{{background:#e5e7eb;color:#111}}
  .danger{{background:var(--warn);color:#fff}}
  .btn.disabled{{opacity:.6;pointer-events:none}}
  .note{{font-size:12px;color:var(--muted);margin-top:8px}}
  @media(max-width:840px){{.grid{{grid-template-columns:1fr}}}}
</style>

<div class="wrap">
  <h1>Gestionar suscripción</h1>
  <p class="muted">Plan actual: <b>{html.escape(current_plan)}</b></p>

  <div class="grid">
    <!-- Columna izquierda: Upgrade -->
    <section class="card">
      <h2 class="plan-name">Mejorar a {html.escape(plan_to_buy)}</h2>
      <p class="price">{amount} <span class="per">/ mes (demo)</span></p>
      <ul>{_render_features(plan_to_buy)}</ul>
      <div class="actions">
        <a class="btn cancel" href="{cancel_url}">Cancelar compra</a>
        <a class="btn pay" href="{pay_url}">Pagar ahora (demo)</a>
        {stripe_btn}
      </div>
      <p class="note">“Pagar ahora (demo)” marca la compra como pagada sin procesador real.</p>
    </section>

    <!-- Columna derecha: Cambiar o cancelar -->
    <aside class="card">
      <h3 style="margin:0 0 8px">Cambiar o cancelar</h3>
      <p class="muted">Puedes bajar de plan o cancelar. Al bajar de plan, se <b>desactivarán</b> mascotas para cumplir el límite. Al cancelar, pasarás a <b>Free</b> y todas tus mascotas quedarán desactivadas.</p>
      <div class="actions" style="justify-content:stretch">
        <a class="btn" href="{to_basic}">Cambiar a Basic</a>
        <a class="btn danger" href="{to_free}">Cancelar (Free)</a>
      </div>
      <p class="note">La desactivación no elimina mascotas; podrás reactivarlas si vuelves a subir de plan.</p>
    </aside>
  </div>
</div>
"""

@app.get("/checkout", response_class=HTMLResponse)
def checkout(t: str | None = None, request: Request = None):
    if not t:
        raise HTTPException(400, "Missing token")
    purchase = _get_purchase(t)
    if not purchase:
        raise HTTPException(404, "Order not found")

    target_plan = purchase["target_plan"]
    uid = purchase["user_id"]
    current_plan = _get_user_plan(uid)
    amount = _amount_for_plan(target_plan)
    return HTMLResponse(_checkout_card_html(target_plan, amount, t, request, current_plan))

@app.get("/checkout/pay")
def checkout_pay(t: str):
    ok, err = db.mark_purchase_paid(t)
    if not ok and err:
        return HTMLResponse(f"<p>Error: {html.escape(err)}</p>", status_code=400)
    return HTMLResponse("""
<!doctype html>
<meta charset="utf-8">
<title>Pago exitoso</title>
<p>✅ ¡Pago exitoso (demo)! Vuelve a la app y refresca tu estado.</p>
""")

@app.get("/checkout/cancel")
def checkout_cancel(t: str):
    db.cancel_purchase(t)
    return HTMLResponse("""
<!doctype html>
<meta charset="utf-8">
<title>Compra cancelada</title>
<p>Operación cancelada.</p>
""")

# --- NUEVO: Downgrade / Cancel (sin pago) ---

@app.get("/checkout/downgrade", response_class=HTMLResponse)
def checkout_downgrade(t: str, to: str):
    to = (to or "Free").strip()
    if to not in ("Free", "Basic", "Plus"):
        raise HTTPException(400, "Plan de destino inválido.")

    ok, err, stats = db.apply_plan_change_by_token(t, to)
    if not ok:
        raise HTTPException(400, err or "No se pudo aplicar el cambio de plan.")

    deact = int(stats.get("deactivated", 0))
    final_plan = stats.get("final_plan", to)

    msg = f"✅ Plan actualizado a <b>{html.escape(final_plan)}</b>."
    if final_plan == "Free":
        sub = "Todas tus mascotas han sido desactivadas."
    else:
        sub = f"{'No hubo' if deact == 0 else f'Se desactivaron {deact} mascota(s)'} para cumplir el límite del plan."

    return HTMLResponse(f"""
<!doctype html>
<meta charset="utf-8">
<title>Cambio de plan</title>
<p>{msg}</p>
<p>{sub}</p>
<p><a href="#" onclick="history.back()">Volver</a></p>
""")

# ---------- Stripe (opcional, igual que antes) ----------

@app.get("/checkout/create-stripe")
def create_stripe_session(t: str, request: Request):
    if not _is_stripe_enabled():
        raise HTTPException(400, "Stripe no está configurado en el servidor.")
    try:
        import stripe
    except Exception:
        raise HTTPException(500, "El paquete 'stripe' no está instalado. pip install stripe")

    purchase = _get_purchase(t)
    if not purchase:
        raise HTTPException(404, "Order not found")

    plan   = purchase["target_plan"]
    amount = _amount_for_plan(plan)
    if amount <= 0:
        raise HTTPException(400, "Monto inválido para Stripe.")

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    success_url = _abs_url(request, f"/checkout/stripe-success?t={t}")
    cancel_url  = _abs_url(request, f"/checkout/cancel?t={t}")
    currency = os.environ.get("STRIPE_CURRENCY", "clp").lower()

    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "product_data": {"name": f"Suscripción {plan} — PetProject"},
                    "unit_amount": amount * 100,
                },
                "quantity": 1,
            }
        ],
        metadata={"external_id": t, "target_plan": plan},
    )
    return RedirectResponse(session.url, status_code=303)

@app.get("/checkout/stripe-success", response_class=HTMLResponse)
def stripe_success(t: str):
    return HTMLResponse("""
<!doctype html>
<meta charset="utf-8">
<title>Pago recibido</title>
<p>✅ ¡Pago recibido en Stripe! Si no ves el plan reflejado aún, espera unos segundos o recarga.</p>
""")

@app.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature")
):
    if not _is_stripe_enabled():
        return PlainTextResponse("Stripe disabled", status_code=400)
    try:
        import stripe
    except Exception:
        return PlainTextResponse("Stripe lib missing", status_code=500)

    payload = await request.body()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    try:
        if secret:
            event = stripe.Webhook.construct_event(
                payload=payload, sig_header=stripe_signature, secret=secret
            )
        else:
            event = json.loads(payload.decode("utf-8"))
    except Exception as e:
        return PlainTextResponse(f"Webhook error: {e}", status_code=400)

    etype = event["type"] if isinstance(event, dict) else event.type
    data  = event["data"]["object"] if isinstance(event, dict) else event.data.object

    if etype == "checkout.session.completed":
        md = data.get("metadata") if isinstance(data, dict) else getattr(data, "metadata", {})
        external_id = (md or {}).get("external_id")
        if external_id:
            db.mark_purchase_paid(external_id)

    return PlainTextResponse("ok")
