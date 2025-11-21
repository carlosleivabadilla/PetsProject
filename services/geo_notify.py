# services/geo_notify.py
from services import db
from services.sms_gateway import send_sms_raw

def notify_geofence(pet_id: int, distance_m: float, left_zone: bool) -> tuple[bool, str | None]:
    """
    Envía un SMS al dueño cuando la mascota sale / entra a la geocerca.
    """
    pet = db.get_pet_with_owner(pet_id)
    if not pet:
        return False, "Mascota no encontrada"

    phone = (pet.get("owner_phone") or "").strip()
    name  = pet.get("name") or "Tu mascota"

    if not phone:
        return False, "El dueño no tiene teléfono registrado"

    if left_zone:
        state = "salió de la zona segura"
    else:
        state = "volvió a la zona segura"

    msg = f"🐾 {name} {state}. Distancia actual: {distance_m:.0f} m aprox."

    return send_sms_raw(phone, msg)
