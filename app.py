# app.py
# --------------------------------------------------------------
# PHY 132 Local Course Hub  —  Offline Streamlit App
# Structure: Modules → Sections (notes + files)
# Local storage:  data/modules.json, uploads/
# --------------------------------------------------------------

import os
import io
import json
import zipfile
import uuid
import hashlib
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from json import JSONDecodeError
import streamlit as st

# -----------------------------
# Config
# -----------------------------
APP_TITLE = "PHY 132 — Local Course Hub"
DB_DIR = Path("data")
DB_PATH = DB_DIR / "modules.json"
UPLOAD_DIR = Path("uploads")
DEFAULT_EDIT_PASSCODE = "eku132"  # change this for security

DEFAULT_DB = {
    "course": {
        "name": "PHY 132: College Physics II",
        "instructor": "Prof. Zakeri • m.zakeri@eku.edu",
        "updated_at": None,
    },
    "modules": [
        {"id": "M0", "title": "Module 0: Foundations", "sections": []},
        {"id": "M1", "title": "Module 1: Electrostatics", "sections": []},
        {"id": "M2", "title": "Module 2: Electric Current & Circuits", "sections": []},
        {"id": "M3", "title": "Module 3: Electromagnetism", "sections": []},
        {"id": "M4", "title": "Module 4: Optics", "sections": []},
    ],
    "version": 2,
}

# -----------------------------
# Helpers
# -----------------------------
def ensure_dirs():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

# ---- Safe JSON DB I/O ----
def save_db(db):
    """Atomic write + automatic backup of old file."""
    db["course"]["updated_at"] = timestamp()
    DB_DIR.mkdir(parents=True, exist_ok=True)
    # Write atomically
    with tempfile.NamedTemporaryFile("w", delete=False, dir=DB_DIR, encoding="utf-8") as tf:
        json.dump(db, tf, indent=2, ensure_ascii=False)
        tmp_name = tf.name
    # backup previous file if it exists
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        backup_path = DB_DIR / f"modules.backup.{datetime.now():%Y%m%d_%H%M%S}.json"
        try:
            shutil.copy2(DB_PATH, backup_path)
        except Exception:
            pass
    os.replace(tmp_name, DB_PATH)

def load_db():
    """Load DB; rebuild if missing or corrupted."""
    ensure_dirs()
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        db = DEFAULT_DB
        db["course"]["updated_at"] = timestamp()
        save_db(db)
        return db
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (JSONDecodeError, OSError, UnicodeDecodeError):
        # rename bad file
        corrupt = DB_DIR / f"modules.corrupt.{datetime.now():%Y%m%d_%H%M%S}.json"
        try:
            shutil.copy2(DB_PATH, corrupt)
        except Exception:
            pass
        db = DEFAULT_DB
        db["course"]["updated_at"] = timestamp()
        save_db(db)
        return db

def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

# -----------------------------
# Data utilities
# -----------------------------
def get_module(db, module_id):
    return next((m for m in db["modules"] if m["id"] == module_id), None)

def get_section(module, section_id):
    return next((s for s in module.get("sections", []) if s["id"] == section_id), None)

def add_module(db, title):
    mod = {"id": new_id("M"), "title": title.strip(), "sections": []}
    db["modules"].append(mod)
    return mod

def add_section(module, title):
    sec = {"id": new_id("S"), "title": title.strip(), "notes": "", "files": []}
    module["sections"].append(sec)
    return sec

def delete_module(db, module_id):
    db["modules"] = [m for m in db["modules"] if m["id"] != module_id]

def delete_section(module, section_id):
    module["sections"] = [s for s in module["sections"] if s["id"] != section_id]

# -----------------------------
# File handling
# -----------------------------
def human_size(n):
    try:
        n = float(n)
    except Exception:
        return "—"
    for u in ["B","KB","MB","GB","TB"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"

def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def save_upload_to_section(section, upload, subdir=""):
    """Button-gated upload with content-hash de-dup."""
    data = upload.read()
    fhash = file_sha256(data)
    if any(f.get("hash") == fhash for f in section.get("files", [])):
        return None, "duplicate"
    folder = UPLOAD_DIR / subdir if subdir else UPLOAD_DIR
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{uuid.uuid4().hex}{Path(upload.name).suffix}"
    with open(dest, "wb") as f:
        f.write(data)
    meta = {
        "name": upload.name,
        "path": str(dest),
        "size": len(data),
        "uploaded_at": timestamp(),
        "hash": fhash,
    }
    section["files"].append(meta)
    return meta, "saved"

# ---- uploads.zip Export/Import ----
def make_uploads_zip() -> bytes:
    """Create a ZIP archive of everything in uploads/."""
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        if UPLOAD_DIR.exists():
            for root, _, files in os.walk(UPLOAD_DIR):
                for name in files:
                    full = Path(root) / name
                    # Keep 'uploads/...' prefix inside the zip
                    arcname = full.relative_to(UPLOAD_DIR.parent)
                    zf.write(full, arcname)
    mem.seek(0)
    return mem.read()

def extract_uploads_zip(zip_bytes: bytes):
    """Extract a ZIP archive into uploads/ (only 'uploads/' paths allowed)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.infolist():
            if not member.filename.startswith("uploads/"):
                continue
            zf.extract(member, path=UPLOAD_DIR.parent)

# -----------------------------
# Sidebar + UI
# -----------------------------
def header(db):
    st.markdown(f"### {APP_TITLE}")
    st.caption(f"{db['course']['name']} • {db['course']['instructor']}")
    st.caption(f"Last updated: {db['course'].get('updated_at','')}")

def sidebar_mode():
    st.sidebar.subheader("View / Edit")
    mode = st.sidebar.radio("Mode", ["Student (read-only)", "Instructor (edit mode)"], index=0)
    ok = False
    if mode == "Instructor (edit mode)":
        pwd = st.sidebar.text_input("Passcode", type="password")
        if pwd == DEFAULT_EDIT_PASSCODE:
            st.sidebar.success("Edit mode enabled.")
            ok = True
        elif pwd:
            st.sidebar.error("Incorrect passcode.")
    return mode, ok

def sidebar_backup_restore(db):
    with st.sidebar.expander("Backup / Restore", expanded=False):
        # --- Database JSON backup ---
        st.download_button(
            "Download DB backup (JSON)",
            data=json.dumps(db, indent=2, ensure_ascii=False),
            file_name="phy132_backup.json",
            mime="application/json",
            use_container_width=True,
        )
        up = st.file_uploader("Import DB backup JSON", type=["json"], key="restore_json")
        if up is not None:
            try:
                newdb = json.loads(up.getvalue().decode("utf-8"))
                if "modules" in newdb and "course" in newdb:
                    save_db(newdb)
                    st.success("Database imported. Reload the app.")
                else:
                    st.error("Invalid structure.")
            except Exception as e:
                st.error(f"Import failed: {e}")

        st.write("---")

        # --- Uploads ZIP backup ---
        st.markdown("**Uploads (all files)**")
        if st.button("Create uploads.zip", use_container_width=True):
            try:
                zip_data = make_uploads_zip()
                st.download_button(
                    "Download uploads.zip",
                    data=zip_data,
                    file_name="uploads.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"ZIP creation failed: {e}")

        zup = st.file_uploader("Import uploads.zip", type=["zip"], key="restore_uploads")
        if zup is not None:
            try:
                extract_uploads_zip(zup.getvalue())
                st.success("Uploads imported.")
            except Exception as e:
                st.error(f"Import failed: {e}")

        st.write("---")
        if st.button("⚠️ Reset to blank database", use_container_width=True):
            try:
                if DB_PATH.exists():
                    backup = DB_DIR / f"modules.reset.{datetime.now():%Y%m%d_%H%M%S}.json"
                    shutil.copy2(DB_PATH, backup)
                    DB_PATH.unlink(missing_ok=True)
            except Exception as e:
                st.error(f"Reset failed: {e}")
            save_db(DEFAULT_DB)
            st.success("Database reset. Reload app.")

# -----------------------------
# Navigation + Views
# -----------------------------
def search_box(db):
    q = st.text_input("Search", placeholder="e.g., lenses, Kirchhoff...")
    if not q:
        return
    ql = q.lower()
    results = []
    for m in db["modules"]:
        for s in m["sections"]:
            hay = (m["title"] + s["title"] + s.get("notes","")).lower()
            fnames = " ".join(f.get("name","") for f in s.get("files", []))
            if ql in hay or ql in fnames:
                results.append((m,s))
    if not results:
        st.info("No matches.")
        return
    st.write(f"**{len(results)} result(s)**")
    for m,s in results:
        with st.container(border=True):
            st.markdown(f"**{m['title']} › {s['title']}**")
            preview = (s.get("notes","") or "")[:240]
            if preview:
                st.caption(preview + ("…" if len(preview)==240 else ""))
            if st.button("Open", key=f"open-{m['id']}-{s['id']}"):
                st.session_state["open_ids"] = {"m":m["id"],"s":s["id"]}
                st.rerun()

def nav_selectors(db):
    ids = st.session_state.get("open_ids", {})
    modules = db["modules"]
    m_idx = next((i for i,m in enumerate(modules) if m["id"]==ids.get("m")),0)
    module = modules[m_idx] if modules else None
    mod_idx = st.selectbox("Module", range(len(modules)), format_func=lambda i:modules[i]["title"], index=m_idx)
    module = modules[mod_idx]
    sections = module["sections"]
    s_idx = next((i for i,s in enumerate(sections) if s["id"]==ids.get("s")),0) if sections else 0
    sec_idx = st.selectbox("Section", range(len(sections)), format_func=lambda i:sections[i]["title"], index=s_idx) if sections else None
    section = sections[sec_idx] if sec_idx is not None and sections else None
    st.session_state.pop("open_ids", None)
    return module, section

def render_section_view(section):
    st.markdown(f"#### {section['title']}")
    if section.get("notes"):
        st.markdown(section["notes"])
    if section.get("files"):
        st.markdown("**Files**")
        for f in section["files"]:
            size = human_size(f.get("size",0))
            col1,col2 = st.columns([3,1])
            with col1:
                st.write(f"• {f['name']}  \n*{size} • {f.get('uploaded_at','')}*")
            with col2:
                try:
                    with open(f["path"],"rb") as fh:
                        st.download_button("Download",data=fh.read(),file_name=f["name"],key=f"dl-{f['path']}")
                except Exception:
                    st.error("Missing file.")

# -----------------------------
# Instructor Tools
# -----------------------------
def edit_tools(db, module, section):
    st.divider()
    st.subheader("Instructor Tools")

    with st.expander("Add / Edit Structure", expanded=True):
        c1,c2 = st.columns(2)
        with c1:
            new_mod = st.text_input("New module title", key="new_mod")
            if st.button("Add module"):
                if new_mod.strip():
                    add_module(db, new_mod)
                    save_db(db); st.rerun()
            if module:
                title = st.text_input("Rename module", value=module["title"])
                if st.button("Save module title"):
                    module["title"]=title; save_db(db); st.rerun()
                if st.button("Delete module", type="primary"):
                    delete_module(db,module["id"]); save_db(db); st.rerun()
        with c2:
            if module:
                new_sec = st.text_input("New section title", key="new_sec")
                if st.button("Add section"):
                    if new_sec.strip():
                        add_section(module,new_sec); save_db(db); st.rerun()
            if section:
                sec_title = st.text_input("Rename section", value=section["title"])
                if st.button("Save section title"):
                    section["title"]=sec_title; save_db(db); st.rerun()
                if st.button("Delete section", type="primary"):
                    delete_section(module,section["id"]); save_db(db); st.rerun()

    if section:
        with st.expander("Section Notes (Markdown)"):
            notes = st.text_area("Notes", value=section.get("notes",""), height=250)
            if st.button("Save notes"):
                section["notes"]=notes; save_db(db); st.success("Saved.")

        with st.expander("Manage Files"):
            key_prefix = f"{section['id']}_uploadkey"
            st.session_state.setdefault(key_prefix,0)
            uploader_key = f"upload_{section['id']}_{st.session_state[key_prefix]}"
            uploads = st.file_uploader("Select files", accept_multiple_files=True, key=uploader_key)
            if st.button("Add files"):
                added,skip=0,0
                if uploads:
                    for u in uploads:
                        _,status=save_upload_to_section(section,u,subdir=section["id"])
                        added+=status=="saved"
                        skip+=status=="duplicate"
                    save_db(db)
                    st.success(f"Added {added}, skipped {skip} duplicate(s).")
                st.session_state[key_prefix]+=1
                st.rerun()

            if section.get("files"):
                st.write("Existing files:")
                keep=[];changed=False
                for f in section["files"]:
                    c1,c2,c3=st.columns([5,2,1])
                    with c1:
                        st.write(f"{f['name']}  \n*{human_size(f.get('size',0))} • {f.get('uploaded_at','')}*")
                    with c2:
                        try:
                            with open(f["path"],"rb") as fh:
                                st.download_button("Download",data=fh.read(),file_name=f["name"],key=f"dl2-{f['path']}")
                        except Exception:
                            st.error("Missing.")
                    with c3:
                        if st.button("❌", key=f"rm-{f['path']}"):
                            try:
                                if os.path.exists(f["path"]): os.remove(f["path"])
                            except Exception: pass
                            changed=True
                        else:
                            keep.append(f)
                if changed:
                    section["files"]=keep; save_db(db); st.rerun()

    with st.expander("Course Info"):
        c=db["course"]
        name=st.text_input("Course name",value=c["name"])
        inst=st.text_input("Instructor line",value=c["instructor"])
        if st.button("Save course info"):
            c["name"]=name; c["instructor"]=inst; save_db(db); st.success("Saved.")

# -----------------------------
# Main
# -----------------------------
def main():
    st.set_page_config(page_title="PHY 132 Local Hub", layout="wide")
    db=load_db()
    header(db)
    mode,can_edit=sidebar_mode()

    # SHOW BACKUP/RESTORE ONLY IN INSTRUCTOR MODE *WITH* CORRECT PASSCODE
    if mode.startswith("Instructor") and can_edit:
        sidebar_backup_restore(db)

    st.markdown("---")
    left,right=st.columns([2,1],vertical_alignment="top")

    with left:
        with st.expander("Search",expanded=False):
            search_box(db)
        st.subheader("Browse")
        module,section=nav_selectors(db)
        if section:
            render_section_view(section)
        else:
            st.info("Select a module and section.")

    with right:
        if mode.startswith("Instructor") and can_edit:
            edit_tools(db,module,section)
        else:
            st.subheader("About")
            st.write(
                "Offline repository of PHY 132 materials. "
                "Instructor mode allows editing and uploads."
            )
            st.markdown(
                "- **Students:** read-only view.\n"
                "- **Instructor:** add/edit content via sidebar.\n"
                "- **Files** live in `uploads/`."
            )

    st.markdown("---")
    st.caption("© Eastern Kentucky University • PHY 132 • Local Course Hub")

if __name__=="__main__":
    main()