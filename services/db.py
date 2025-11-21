# services/db.py
import sqlite3, os, hashlib, uuid, secrets
import json, urllib.request
import math
try:
    import requests  # <-- para llamar a tu gateway SMS
except Exception:
    requests = None

DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")

# ========== Configuración SMS ==========

_SMS_GATEWAY_URL: str|None = None

def configure_sms_gateway(url: str|None=None):
    global _SMS_GATEWAY_URL
    if url:
        _SMS_GATEWAY_URL = url.strip()

def _get_sms_url()->str:
    global _SMS_GATEWAY_URL

    url = (_SMS_GATEWAY_URL or "").strip()

    if not url:
        url = os.environ.get("SMS_GATEWAY_URL","").strip()

    if not url:
        try:
            with open("SMS_GATEWAY.json","r",encoding="utf-8") as f:
                data = json.load(f)
            url = (data.get("url") or "").strip()
        except Exception:
            pass
    return url

def _send_sms(phone: str, text: str) -> bool:
    """
    Envía un SMS usando tu Simple SMS Gateway.

    - Usa SMS_GATEWAY_URL desde variables de entorno.
    - Formato esperado por tu servidor:
        POST { "phone": "...", "message": "..." } como JSON.
    - Devuelve True si aparentemente salió bien, False si falló.
    """
    url = _get_sms_url()

    if not url:
        print("[SMS] SMS_GATEWAY_URL no configurado; no se envía nada.")
        return False

    phone = (phone or "").strip()
    text = (text or "").strip()
    if not phone or not text:
        print("[SMS] Teléfono o texto vacíos; no se envía nada.")
        return False

    payload = {
        "phone": phone,   # número que viene del perfil del usuario
        "message": text,  # texto del aviso
    }

    try:
        # 1) Si tenemos 'requests' (PC/backend), úsalo
        if requests is not None:
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code >= 400:
                print(f"[SMS] Error {resp.status_code}: {resp.text}")
                return False

            print("[SMS] Enviado vía requests:", resp.status_code, resp.text[:200])
            return True

        # 2) Fallback para Android: urllib.request (lib estándar)
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = getattr(resp, "status", resp.getcode())
            body = resp.read().decode("utf-8", errors="ignore")
            if status >= 400:
                print(f"[SMS] Error {status}: {body[:200]}")
                return False

            print("[SMS] Enviado vía urllib:", status, body[:200])
        return True

    except Exception as e:
        print("[SMS] Error enviando SMS:", e)
        return False

def _conn():
    conn = sqlite3.connect(DB_PATH)
    return conn

def _hash(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

# =========================
# Migraciones tablas
# =========================

def _ensure_user_columns(c):
    cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    if "name" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN name TEXT DEFAULT ''")
    if "phone" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''")
    if "plan" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'Free'")
    if "role" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    # ubicación de residencia para geocerca
    if "home_lat" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN home_lat REAL")
    if "home_lng" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN home_lng REAL")
    if "home_address" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN home_address TEXT")

def _ensure_pets_columns(c):
    cols = {r[1] for r in c.execute("PRAGMA table_info(pets)").fetchall()}

    if "user_id" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN user_id INTEGER")

    if "status" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN status TEXT DEFAULT 'active'")

    if "tracker_code" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN tracker_code TEXT")

    if "last_lat" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN last_lat REAL")

    if "last_lng" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN last_lng REAL")

    if "last_at" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN last_at TEXT")

    if "requested_by" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN requested_by INTEGER")

    if "requested_at" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN requested_at TEXT")

    if "approved_by" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN approved_by INTEGER")

    if "approved_at" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN approved_at TEXT")

    if "qr_token" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN qr_token TEXT")

    # estado de geocerca (inside / outside / unknown)
    if "geofence_state" not in cols:
        c.execute("ALTER TABLE pets ADD COLUMN geofence_state TEXT DEFAULT 'unknown'")

# =========================
# Geocerca + SMS
# =========================

def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distancia aproximada entre 2 puntos (lat/lon en grados) en metros.
    """
    R = 6371000.0  # radio terrestre en metros
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _check_geofence_and_notify(conn, pet_id: int, user_id: int, lat: float, lng: float):
    """
    Comprueba si la mascota salió de la geocerca y, si cambia de estado 'inside' -> 'outside',
    envía una notificación por SMS usando tu gateway local.
    """
    c = conn.cursor()

    # 1) Datos de usuario (residencia + teléfono)
    row_u = c.execute(
        "SELECT home_lat, home_lng, phone, name FROM users WHERE id=?",
        (user_id,)
    ).fetchone()
    if not row_u:
        return

    home_lat, home_lng, phone, owner_name = row_u

    if home_lat is None or home_lng is None:
        # No hay geocerca configurada
        return
    phone = (phone or "").strip()
    if not phone:
        # No hay teléfono para notificar
        return

    # 2) Estado previo de geocerca
    row_p = c.execute(
        "SELECT geofence_state, name FROM pets WHERE id=?",
        (pet_id,)
    ).fetchone()
    if not row_p:
        return

    prev_state, pet_name = row_p
    prev_state = (prev_state or "unknown").lower()
    pet_name = pet_name or "tu mascota"

    # 3) Distancia actual
    dist_m = _haversine_distance_m(home_lat, home_lng, lat, lng)
    RADIUS = 20.0  # metros

    new_state = "inside" if dist_m <= RADIUS else "outside"

    # 4) Si no cambió de estado, no hacemos nada
    if new_state == prev_state:
        return

    # 5) Actualiza estado
    c.execute(
        "UPDATE pets SET geofence_state=? WHERE id=?",
        (new_state, pet_id)
    )
    conn.commit()

    # 6) Si acaba de salir (inside/unknown -> outside), enviamos SMS
    if new_state == "outside":
        msg = (
            f"⚠️ {pet_name} salió de la zona segura.\n"
            f"Distancia aproximada a casa: {dist_m:.1f} m."
        )
        _send_sms(phone, msg)

def _backfill_qr_tokens(c):
    """Asigna qr_token a las mascotas que aún no lo tengan."""
    rows = c.execute("SELECT id FROM pets WHERE qr_token IS NULL OR qr_token=''").fetchall()
    for (pid,) in rows:
        c.execute("UPDATE pets SET qr_token=? WHERE id=?", (uuid.uuid4().hex, pid))

def _ensure_qr_unique_index(c):
    """Índice único sobre qr_token (permite NULLs)."""
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pets_qr_token ON pets(qr_token)")

def init_db():
    with _conn() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'Free',
                role TEXT NOT NULL DEFAULT 'user',
                name TEXT DEFAULT '',
                phone TEXT DEFAULT ''
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pets(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                breed TEXT,
                photo TEXT
            )
        """)
        # Checkout / “compras”
        c.execute("""
            CREATE TABLE IF NOT EXISTS purchases(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                target_plan TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',   -- pending | paid | canceled
                provider TEXT NOT NULL DEFAULT 'mock',    -- luego: 'stripe', 'mp', etc
                external_id TEXT UNIQUE,                  -- token/ID de la orden
                amount_cents INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        _ensure_user_columns(c)
        _ensure_pets_columns(c)
        _backfill_qr_tokens(c)
        _ensure_qr_unique_index(c)
        conn.commit()

        # seed admin
        admin_email = "admin@admin.cl"
        exists = c.execute(
            "SELECT 1 FROM users WHERE email=?",
            (admin_email,)      # ← coma al final: esto SÍ es una tupla de 1 elemento
        ).fetchone()
        if not exists:
            c.execute(
                "INSERT INTO users(email, password_hash, plan, role, name, phone) VALUES(?,?,?,?,?,?)",
                (admin_email, _hash("admin123"), "Owner", "admin", "Admin", "")
            )
            conn.commit()

# =========================
# Planes y límites
# =========================

_PLAN_LIMITS = {
    "Free": 0,
    "Basic": 1,
    "Plus":  5,
    # "Owner": ilimitado
}

def plan_limit(plan: str) -> int:
    """Límite de mascotas activas para el plan (Owner = sin límite práctico)."""
    if (plan or "").strip() == "Owner":
        return 999_999
    return _PLAN_LIMITS.get((plan or "Free").strip(), 0)

def _get_user_plan_role(user_id: int):
    with _conn() as conn:
        row = conn.execute("SELECT plan, role FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return "Free", "user"
        return row[0] or "Free", row[1] or "user"

def count_user_pets(user_id: int, include_rejected: bool = False) -> int:
    with _conn() as conn:
        if include_rejected:
            row = conn.execute("SELECT COUNT(*) FROM pets WHERE user_id=?", (user_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM pets WHERE user_id=? AND status IN ('active','pending')",
                (user_id,)
            ).fetchone()
        return int(row[0] if row else 0)

def count_user_active_pets(user_id: int) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM pets WHERE user_id=? AND status='active'",
            (user_id,)
        ).fetchone()
        return int(row[0] if row else 0)

def count_user_active_plus_pending_pets(user_id: int) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM pets WHERE user_id=? AND status IN ('active','pending')",
            (user_id,)
        ).fetchone()
        return int(row[0] if row else 0)

def can_user_add_pet(user_id: int):
    """Devuelve (ok, reason).

    Valida contra el límite del plan usando ACTIVAS + PENDIENTES (no solo activas).
    Free: 0, Basic: 1, Plus: 5. Admin/Owner sin límite.
    """
    plan, role = _get_user_plan_role(user_id)

    # Admin y Owner sin límite
    if role == "admin" or (plan or "").strip() == "Owner":
        return True, None

    limit = plan_limit(plan)
    total = count_user_active_plus_pending_pets(user_id)

    if total >= limit:
        if limit == 0:
            return False, "Tu plan actual no permite registrar mascotas. Mejora tu plan para poder agregar una."
        return False, f"Tu plan ({plan}) permite hasta {limit} mascota(s) activas o en revisión."

    return True, None

def can_user_downgrade_to(user_id: int, new_plan: str) -> tuple[bool, str | None]:
    """Evita bajar a un plan con menos cupo del que ya tiene activo."""
    if (new_plan or "").strip() == "Owner":
        return True, None
    limit = plan_limit(new_plan)
    active_now = count_user_active_pets(user_id)
    if active_now > limit:
        return False, (f"No puedes bajar a {new_plan}: ya tienes {active_now} mascota(s) activas "
                       f"y el límite es {limit}.")
    return True, None

# =========================
# Users / Auth
# =========================

def auth(email: str, password: str):
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT id, email, plan, role, name, phone, home_address, home_lat, home_lng, password_hash
              FROM users
             WHERE email=?
            """,
            (email.strip().lower(),)
        ).fetchone()
        if not row:
            return None
        uid, em, plan, role, name, phone, home_address, home_lat, home_lng, pwh = row
        if pwh != _hash(password):
            return None
        return {
            "id": uid,
            "email": em,
            "plan": (plan or "Free").strip(),
            "role": role or "user",
            "name": name or "",
            "phone": phone or "",
            "home_address": home_address or "",
            "home_lat": home_lat,
            "home_lng": home_lng,
        }

def register(email: str, password: str, name: str, phone: str):
    with _conn() as conn:
        try:
            conn.execute(
                "INSERT INTO users(email, password_hash, plan, role, name, phone) VALUES(?,?,?,?,?,?)",
                (email.strip().lower(), _hash(password), "Free", "user", name.strip(), phone.strip())
            )
            conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)

def list_users():
    with _conn() as conn:
        rows = conn.execute("SELECT id, email, name, phone, plan, role FROM users").fetchall()
    admins = [r for r in rows if r[5] == "admin"]
    others = sorted([r for r in rows if r[5] != "admin"], key=lambda x: (x[5], x[1]))
    return admins + others

def update_user_plan(user_id: int, new_plan: str):
    with _conn() as conn:
        role = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if role and role[0] == "admin":
            return False, "No se puede cambiar la suscripción del administrador."
        conn.execute("UPDATE users SET plan=? WHERE id=?", (new_plan, user_id))
        conn.commit()
        return True, None

def count_orphan_pets() -> int:
    with _conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM pets WHERE user_id IS NULL").fetchone()
        return int(row[0] if row else 0)

def attach_orphan_pets_to_user(user_id: int) -> int:
    with _conn() as conn:
        cur = conn.execute("UPDATE pets SET user_id=? WHERE user_id IS NULL", (user_id,))
        conn.commit()
        return cur.rowcount

def update_user_profile(
    user_id: int,
    name: str,
    phone: str,
    home_address: str | None = None,
    home_lat: float | None = None,
    home_lng: float | None = None,
):
    """
    Actualiza perfil del usuario.
    - Si no se pasan home_* se actualiza solo nombre/teléfono (compatibilidad).
    - Si se pasan home_* se guardan también dirección y coordenadas.
    """
    name  = (name or "").strip()
    phone = (phone or "").strip()

    with _conn() as conn:
        if home_address is None and home_lat is None and home_lng is None:
            # Modo antiguo (solo nombre/teléfono)
            conn.execute(
                "UPDATE users SET name=?, phone=? WHERE id=?",
                (name, phone, user_id),
            )
        else:
            conn.execute(
                """
                UPDATE users
                   SET name=?,
                       phone=?,
                       home_address=?,
                       home_lat=?,
                       home_lng=?
                 WHERE id=?
                """,
                (
                    name,
                    phone,
                    (home_address or "").strip(),
                    home_lat,
                    home_lng,
                    user_id,
                ),
            )
        conn.commit()

def delete_user_and_pets(user_id: int):
    with _conn() as conn:
        role = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if role and role[0] == "admin":
            return False, "No se puede eliminar la cuenta del administrador."
        conn.execute("DELETE FROM pets WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        return True, None

def delete_user_pets(user_id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM pets WHERE user_id=?", (user_id,))
        conn.commit()

def get_user_by_id(user_id: int):
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT id, email, plan, role, name, phone, home_address, home_lat, home_lng
              FROM users
             WHERE id=?
            """,
            (user_id,)
        ).fetchone()
    if not row:
        return None
    uid, email, plan, role, name, phone, home_address, home_lat, home_lng = row
    return {
        "id": uid,
        "email": email,
        "plan": (plan or "Free").strip(),
        "role": role or "user",
        "name": name or "",
        "phone": phone or "",
        "home_address": home_address or "",
        "home_lat": home_lat,
        "home_lng": home_lng,
    }

# =========================
# Pets (con estados)
# =========================

def list_user_pets(user_id: int, include_pending: bool = False):
    with _conn() as conn:
        if include_pending:
            return conn.execute(
                "SELECT id, name, breed, photo FROM pets WHERE user_id=? ORDER BY id DESC",
                (user_id,)
            ).fetchall()
        else:
            return conn.execute(
                "SELECT id, name, breed, photo FROM pets WHERE user_id=? AND status='active' ORDER BY id DESC",
                (user_id,)
            ).fetchall()

def list_user_all_pets(user_id: int):
    with _conn() as conn:
        return conn.execute(
            "SELECT id, name, breed, photo FROM pets WHERE user_id=? ORDER BY id DESC",
            (user_id,)
        ).fetchall()

def list_user_all_pets_with_status(user_id: int):
    """Todas las mascotas (activas, pendientes, inactivas) con su status."""
    with _conn() as conn:
        return conn.execute(
            "SELECT id, name, breed, photo, status FROM pets WHERE user_id=? ORDER BY id DESC",
            (user_id,)
        ).fetchall()

def add_pet(name: str, breed: str, photo: str, user_id: int | None = None):
    """Alta directa (estado 'active'), respetando límites. Genera qr_token."""
    if user_id:
        ok, reason = can_user_add_pet(user_id)
        if not ok:
            raise ValueError(reason)
    with _conn() as conn:
        tok = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO pets(name, breed, photo, user_id, qr_token) VALUES(?,?,?,?,?)",
            (name, breed, photo, user_id, tok)
        )
        conn.commit()

def delete_pet(pid: int):
    with _conn() as conn:
        conn.execute("DELETE FROM pets WHERE id=?", (pid,))
        conn.commit()

def rename_pet(pid: int, new_name: str):
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("El nombre no puede estar vacío.")
    with _conn() as conn:
        conn.execute("UPDATE pets SET name=? WHERE id=?", (new_name, pid))
        conn.commit()

def request_add_pet(name: str, breed: str, photo: str, requested_by: int):
    """Crea mascota en estado 'pending' respetando límites y con qr_token."""
    ok, reason = can_user_add_pet(requested_by)
    if not ok:
        raise ValueError(reason)
    with _conn() as conn:
        tok = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO pets(name, breed, photo, user_id, status, requested_by, requested_at, qr_token)
            VALUES (?,?,?,?, 'pending', ?, datetime('now'), ?)
            """,
            (name, breed, photo, requested_by, requested_by, tok)
        )
        conn.commit()

def approve_pet(pet_id: int, admin_id: int):
    """Aprueba solicitud → pasa a 'active', validando cupo de activas."""
    # dueño
    with _conn() as conn:
        row = conn.execute("SELECT user_id FROM pets WHERE id=?", (pet_id,)).fetchone()
        if not row:
            return
        uid = row[0]

    plan, role = _get_user_plan_role(uid)
    if not (role == "admin" or plan == "Owner"):
        limit = plan_limit(plan)
        active_now = count_user_active_pets(uid)
        if active_now >= limit:
            raise ValueError(
                f"No se puede aprobar: el usuario ya tiene {active_now} mascota(s) activas; "
                f"su plan ({plan}) permite hasta {limit}."
            )

    with _conn() as conn:
        conn.execute(
            """
            UPDATE pets
               SET status='active',
                   approved_by=?,
                   approved_at=datetime('now')
             WHERE id=?
            """,
            (admin_id, pet_id)
        )
        conn.commit()

def reject_pet(pet_id: int, admin_id: int | None = None):
    """Antes: marcaba 'rejected'. Ahora: elimina la mascota definitivamente."""
    with _conn() as conn:
        conn.execute("DELETE FROM pets WHERE id=?", (pet_id,))
        conn.commit()

def list_pending_pets():
    with _conn() as conn:
        return conn.execute(
            """
            SELECT p.id, p.name, p.breed, p.photo, p.user_id,
                   u.email, u.name, p.requested_at
              FROM pets p
              LEFT JOIN users u ON u.id = p.user_id
             WHERE p.status='pending'
             ORDER BY p.requested_at DESC, p.id DESC
            """
        ).fetchall()

def count_pending_for_user(user_id: int) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM pets WHERE user_id=? AND status='pending'",
            (user_id,)
        ).fetchone()
        return int(row[0] if row else 0)

# =========================
# QR token & ubicación
# =========================

def _ensure_qr_token(conn, pet_id: int) -> str:
    """Crea un qr_token si no existe para esa mascota y lo devuelve."""
    c = conn.cursor()
    row = c.execute("SELECT qr_token FROM pets WHERE id=?", (pet_id,)).fetchone()
    token = (row[0] if row else None)
    if token:
        return token
    # crea uno nuevo (maneja posible colisión por índice único)
    while True:
        token = secrets.token_hex(16)
        try:
            c.execute("UPDATE pets SET qr_token=? WHERE id=?", (token, pet_id))
            conn.commit()
            return token
        except Exception:
            continue  # intenta con otro token

def get_pet_qr_payload(pet_id: int) -> str:
    """Devuelve URL pública si hay base detectable; si no, payload offline con token."""
    with _conn() as conn:
        token = _ensure_qr_token(conn, pet_id)

    base = _autodetect_public_base()
    if base:
        return f"{base}/p?t={token}"

    # fallback offline
    return f"PETTOKEN:{token}"

def get_public_pet_info_by_token(token: str):
    """Info pública para la página /p?t=..."""
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT p.id, p.name, p.photo,
                   u.name, u.phone
              FROM pets p
              LEFT JOIN users u ON u.id = p.user_id
             WHERE p.qr_token=?
            """,
            (token,)
        ).fetchone()
        if not row:
            return None
        pid, pet_name, photo, owner_name, owner_phone = row
        return {
            "pet_id": pid,
            "pet_name": pet_name or "Sin nombre",
            "photo": photo or "",
            "owner_name": owner_name or "",
            "owner_phone": (owner_phone or "").strip(),
        }

def get_pet(pid: int):
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT
                id,
                name,
                breed,
                photo,
                tracker_code,
                last_lat,
                last_lng,
                last_at,
                geofence_state
            FROM pets
            WHERE id=?
            """,
            (pid,),
        ).fetchone()

    if not row:
        return None

    keys = [
        "id",
        "name",
        "breed",
        "photo",
        "tracker_code",
        "last_lat",
        "last_lng",
        "last_at",
        "geofence_state",
    ]
    return dict(zip(keys, row))

def set_pet_tracker(pid: int, tracker_code: str | None):
    with _conn() as conn:
        conn.execute("UPDATE pets SET tracker_code=? WHERE id=?", (tracker_code, pid))
        conn.commit()

def update_location_by_pet(pid: int, lat: float, lng: float):
    with _conn() as conn:
        c = conn.cursor()
        # Actualiza ubicación
        c.execute(
            "UPDATE pets SET last_lat=?, last_lng=?, last_at=datetime('now') WHERE id=?",
            (lat, lng, pid)
        )
        # Obtenemos el user_id para geocerca
        row = c.execute("SELECT user_id FROM pets WHERE id=?", (pid,)).fetchone()
        conn.commit()

        if row and row[0]:
            try:
                _check_geofence_and_notify(conn, pet_id=pid, user_id=row[0], lat=lat, lng=lng)
            except Exception as ex:
                print("[Geofence] Error en update_location_by_pet:", ex)

def update_location_by_tracker(tracker_code: str, lat: float, lng: float):
    with _conn() as conn:
        c = conn.cursor()
        # Actualiza ubicación
        c.execute(
            "UPDATE pets SET last_lat=?, last_lng=?, last_at=datetime('now') WHERE tracker_code=?",
            (lat, lng, tracker_code)
        )
        # Buscamos la mascota asociada al tracker
        row = c.execute(
            "SELECT id, user_id FROM pets WHERE tracker_code=?",
            (tracker_code,)
        ).fetchone()
        conn.commit()

        if row and row[0] and row[1]:
            pid, uid = row
            try:
                _check_geofence_and_notify(conn, pet_id=pid, user_id=uid, lat=lat, lng=lng)
            except Exception as ex:
                print("[Geofence] Error en update_location_by_tracker:", ex)

def get_pet_with_owner(pid: int):
    """Mascota + dueño."""
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT p.id, p.name, p.breed, p.photo, p.tracker_code, p.last_lat, p.last_lng, p.last_at,
                   p.user_id, u.email, u.name, u.phone
              FROM pets p
         LEFT JOIN users u ON u.id = p.user_id
             WHERE p.id=?
            """,
            (pid,)
        ).fetchone()
        if not row:
            return None
        keys = ["id","name","breed","photo","tracker_code","last_lat","last_lng","last_at",
                "user_id","owner_email","owner_name","owner_phone"]
        return dict(zip(keys, row))

# =========================
# “Checkout” simulado
# =========================

def create_checkout_order(user_id: int, target_plan: str, amount_cents: int = 0) -> tuple[bool, str | None, str | None]:
    """
    Crea una orden 'pending' y devuelve (ok, checkout_url, error).
    JAMÁS permite 'Owner' como target para usuarios (solo Free/Basic/Plus).
    También evita “no-upgrades” (mismo plan o inferior).
    """
    # Normaliza y bloquea Owner
    target_plan = (target_plan or "").strip()
    if target_plan not in ("Free", "Basic", "Plus"):
        return False, None, "Plan inválido."

    current_plan, role = _get_user_plan_role(user_id)
    if role == "admin":
        return False, None, "El admin no necesita cambiar plan."

    # ranking sin Owner
    rank = ["Free", "Basic", "Plus"]
    try:
        cur_idx = rank.index(current_plan if current_plan in rank else "Free")
        tgt_idx = rank.index(target_plan)
    except ValueError:
        return False, None, "Plan inválido."

    if tgt_idx <= cur_idx:
        return False, None, f"Ya estás en {current_plan} o superior."

    ext_id = uuid.uuid4().hex
    with _conn() as conn:
        conn.execute(
            "INSERT INTO purchases(user_id, target_plan, status, provider, external_id, amount_cents) VALUES(?,?,?,?,?,?)",
            (user_id, target_plan, "pending", "mock", ext_id, amount_cents)
        )
        conn.commit()

    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        base = "http://localhost:8000"
    checkout_url = f"{base}/checkout?t={ext_id}"
    return True, checkout_url, None

def mark_purchase_paid(external_id: str) -> tuple[bool, str | None]:
    """
    Marca compra pagada y aplica el plan al usuario **usando change_user_plan**,
    de modo que:
      - Se reactiven mascotas inactivas hasta el cupo del nuevo plan.
      - Se desactiven las sobrantes si corresponde.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, user_id, target_plan, status FROM purchases WHERE external_id=?",
            (external_id,)
        ).fetchone()

    if not row:
        return False, "Orden no encontrada."

    pid, uid, target_plan, status = row

    # Si ya está pagada, no repetimos cambios; asumimos que el plan ya se aplicó.
    if status == "paid":
        return True, None

    if status == "canceled":
        return False, "La orden fue cancelada."

    # Usa la lógica centralizada (reactiva inactivas, respeta límites, etc.)
    ok, err, _stats = change_user_plan(uid, target_plan)
    if not ok:
        return False, err or "No se pudo aplicar el nuevo plan."

    # Marca la compra como pagada
    with _conn() as conn:
        conn.execute("UPDATE purchases SET status='paid' WHERE id=?", (pid,))
        conn.commit()

    return True, None

def cancel_purchase(external_id: str):
    with _conn() as conn:
        conn.execute("UPDATE purchases SET status='canceled' WHERE external_id=?", (external_id,))
        conn.commit()

def _autodetect_public_base() -> str:
    """
    1) Si existe PUBLIC_BASE_URL en el entorno -> úsalo.
    2) Si hay ngrok corriendo local (API 4040) -> usa la URL https pública.
    3) Si existe PUBLIC_BASE_URL.txt -> lee y usa su contenido.
    4) Si nada de lo anterior -> cadena vacía (se usa token).
    """
    base = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if base:
        return base.rstrip("/")

    # ngrok local
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=0.7) as r:
            data = json.load(r)
            for t in data.get("tunnels", []):
                if t.get("proto") == "https" and t.get("public_url"):
                    return t["public_url"].rstrip("/")
    except Exception:
        pass

    # archivo local
    try:
        with open("PUBLIC_BASE_URL.txt", "r", encoding="utf-8") as f:
            txt = f.read().strip()
            if txt:
                return txt.rstrip("/")
    except Exception:
        pass

    return ""

def get_or_create_qr_token(pet_id: int) -> str:
    """Devuelve el qr_token estable; si no existe, lo crea y lo persiste."""
    with _conn() as conn:
        c = conn.cursor()
        row = c.execute("SELECT qr_token FROM pets WHERE id=?", (pet_id,)).fetchone()
        tok = row[0] if row else None
        if tok:
            return tok
        # crea token nuevo cuidando colisiones (por índice único)
        while True:
            tok = secrets.token_hex(16)
            try:
                c.execute("UPDATE pets SET qr_token=? WHERE id=?", (tok, pet_id))
                conn.commit()
                return tok
            except Exception:
                continue

def _rank_order():
    return ["Free", "Basic", "Plus", "Owner"]

def _plan_limit(plan: str) -> int:
    return _PLAN_LIMITS.get(plan, 0)

def _list_active_pet_ids_ordered(conn, user_id: int):
    """
    Devuelve IDs de mascotas activas del usuario ordenadas por 'approved_at' DESC, luego id DESC.
    Mantiene primero las más nuevas, que son las que 'sobreviven'.
    """
    return [
        r[0]
        for r in conn.execute(
            """
            SELECT id FROM pets
            WHERE user_id=? AND status='active'
            ORDER BY COALESCE(approved_at,'1970-01-01') DESC, id DESC
            """,
            (user_id,)
        ).fetchall()
    ]

def deactivate_all_user_pets(user_id: int) -> int:
    """Desactiva TODAS las mascotas del usuario (para cancelación → Free)."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE pets SET status='inactive' WHERE user_id=? AND status='active'",
            (user_id,)
        )
        conn.commit()
        return cur.rowcount

def enforce_plan_limits(user_id: int, plan: str) -> tuple[int, int]:
    """
    Garantiza que el usuario cumpla el límite de su plan.
    Devuelve (activas_finales, desactivadas).
    - Owner/admin: sin cambios.
    - Free: desactiva todas.
    - Basic/Plus: deja activas las N más recientes y desactiva el resto.
    """
    plan = (plan or "Free").strip()
    with _conn() as conn:
        # Admin/Owner: sin límite
        role_row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        role = (role_row[0] if role_row else "user")
        if role == "admin" or plan == "Owner":
            n = conn.execute("SELECT COUNT(*) FROM pets WHERE user_id=? AND status='active'", (user_id,)).fetchone()
            return int(n[0] if n else 0), 0

        if plan == "Free":
            cur = conn.execute("UPDATE pets SET status='inactive' WHERE user_id=? AND status='active'", (user_id,))
            conn.commit()
            return 0, cur.rowcount

        limit = _plan_limit(plan)
        ids = _list_active_pet_ids_ordered(conn, user_id)
        if len(ids) <= limit:
            return len(ids), 0

        keep = set(ids[:limit])
        drop = [pid for pid in ids if pid not in keep]
        if drop:
            conn.executemany("UPDATE pets SET status='inactive' WHERE id=?", [(pid,) for pid in drop])
            conn.commit()
        return limit, len(drop)

def _list_inactive_pet_ids_ordered(conn, user_id: int):
    """
    IDs de mascotas inactivas ordenadas (más recientes primero) para reactivar primero las últimas.
    """
    return [
        r[0]
        for r in conn.execute(
            """
            SELECT id FROM pets
             WHERE user_id=? AND status='inactive'
             ORDER BY COALESCE(approved_at,'1970-01-01') DESC, id DESC
            """,
            (user_id,)
        ).fetchall()
    ]

def reactivate_up_to_plan_limit(user_id: int, plan: str | None = None) -> int:
    """
    Reactiva, si corresponde, mascotas 'inactive' hasta completar el cupo del plan.
    Devuelve cuántas se reactivaron.
    """
    if plan is None:
        plan, role = _get_user_plan_role(user_id)
    else:
        role = _get_user_plan_role(user_id)[1]

    if role == "admin" or plan == "Owner":
        return 0  # sin límites

    limit = plan_limit(plan)
    if limit <= 0:
        return 0

    with _conn() as conn:
        active_now = conn.execute(
            "SELECT COUNT(*) FROM pets WHERE user_id=? AND status='active'", (user_id,)
        ).fetchone()
        active_now = int(active_now[0] if active_now else 0)
        if active_now >= limit:
            return 0

        need = limit - active_now
        ids = _list_inactive_pet_ids_ordered(conn, user_id)[:need]
        if not ids:
            return 0

        conn.executemany("UPDATE pets SET status='active', approved_at=datetime('now') WHERE id=?", [(i,) for i in ids])
        conn.commit()
        return len(ids)

def change_user_plan(user_id: int, new_plan: str) -> tuple[bool, str | None, dict]:
    """
    Cambia el plan del usuario y ajusta sus mascotas:
    - Si el plan tiene cupo > 0, intenta reactivar mascotas inactivas
      (las más recientes primero) hasta llenar el cupo.
    - Si hay más activas de las permitidas, desactiva las más antiguas.
    Devuelve (ok, error, stats) donde stats = {"activated", "deactivated", "final_plan"}.
    """
    new_plan = (new_plan or "Free").strip()

    # Cambiamos el plan en la tabla users
    with _conn() as conn:
        role_row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if not role_row:
            return False, "Usuario no existe.", {}
        role = role_row[0]
        if role == "admin":
            return False, "El admin no necesita cambiar plan.", {}

        conn.execute("UPDATE users SET plan=? WHERE id=?", (new_plan, user_id))
        conn.commit()

    # 1) Intentar reactivar mascotas inactivas hasta llenar el cupo del nuevo plan
    activated = reactivate_up_to_plan_limit(user_id, new_plan)

    # 2) Enforce de límites por si, por alguna razón, quedamos pasados de cupo
    active_before = count_user_active_pets(user_id)
    active_after, deactivated = enforce_plan_limits(user_id, new_plan)

    return True, None, {
        "activated": activated if activated is not None else max(active_after - max(active_before, 0), 0),
        "deactivated": deactivated,
        "final_plan": new_plan,
    }

def apply_plan_change_by_token(external_id: str, target_plan: str) -> tuple[bool, str | None, dict]:
    """
    Cambia el plan asociado a un token de 'purchases' (sin cobro), útil para downgrades/cancel.
    Marca la purchase como 'paid' para cerrar el flujo.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, user_id, status FROM purchases WHERE external_id=?", (external_id,)
        ).fetchone()
        if not row:
            return False, "Orden no encontrada.", {}
        pid, uid, status = row

    ok, err, stats = change_user_plan(uid, target_plan)
    if not ok:
        return False, err, stats

    with _conn() as conn:
        conn.execute("UPDATE purchases SET status='paid' WHERE external_id=?", (external_id,))
        conn.commit()

    return True, None, stats
