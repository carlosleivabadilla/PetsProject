# tools/migrate_pet_photos.py
import os, base64, mimetypes, sqlite3

DB = "services/app.db"  # ajusta si tu DB está en otra ruta

def to_data_url(fs_path: str) -> str | None:
    if not os.path.exists(fs_path):
        return None
    mime, _ = mimetypes.guess_type(fs_path)
    mime = mime or "image/jpeg"
    with open(fs_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def run():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT id, photo FROM pets")
    rows = cur.fetchall()
    updated = 0
    for pid, photo in rows:
        if not photo:
            continue
        p = str(photo)
        if p.startswith("data:") or p.startswith("/assets/"):
            continue
        # normaliza posibles rutas relativas desde uploads/
        cand = p.replace("\\", "/")
        if cand.startswith("uploads/") or cand.startswith("./uploads/"):
            fs_path = cand
        else:
            # prueba dentro de ./uploads por si guardaste solo el nombre
            fs_path = os.path.join("uploads/pets", os.path.basename(cand))

        fs_path = fs_path.replace("/", os.sep)

        data_url = to_data_url(fs_path)
        if data_url:
            cur.execute("UPDATE pets SET photo=? WHERE id=?", (data_url, pid))
            updated += 1
    con.commit()
    con.close()
    print(f"Actualizadas a base64: {updated}")

if __name__ == "__main__":
    run()
