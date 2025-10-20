# app.py
# ---------------------------------------------
# PHY 132 Local Course Hub (offline-ready)
# Modules → Sections → (notes + files). No pages.
# - Local JSON DB:   ./data/modules.json
# - Upload storage:  ./uploads/
# - Backup/restore via sidebar
# ---------------------------------------------

import os
import json
import uuid
import hashlib
from datetime import datetime
from pathlib import Path

import streamlit as st

# -------------------------
# Config
# -------------------------
APP_TITLE = "PHY 132 — Local Course Hub"
DB_DIR = Path("data")
DB_PATH = DB_DIR / "modules.json"
UPLOAD_DIR = Path("uploads")
DEFAULT_EDIT_PASSCODE = "eku132"  # change this

# Seed modules aligned with your course (used only on first run)
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
    "version": 2,  # bump when structure changes
}

# -------------------------
# Helpers (DB I/O)
# -------------------------
def ensure_dirs():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def save_db(db):
    db["course"]["updated_at"] = timestamp()
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def load_db():
    ensure_dirs()
    if not DB_PATH.exists():
        db = DEFAULT_DB
        db["course"]["updated_at"] = timestamp()
        save_db(db)
        return db
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

# -------------------------
# Data structure utilities (no pages)
# -------------------------
def get_module(db, module_id):
    return next((m for m in db["modules"] if m["id"] == module_id), None)

def get_section(module, section_id):
    return next((s for s in module.get("sections", []) if s["id"] == section_id), None)

def add_module(db, title):
    mod = {"id": new_id("M"), "title": title.strip(), "sections": []}
    db["modules"].append(mod)
    return mod

def add_section(module, title):
    # each section has optional markdown notes + files list
    sec = {"id": new_id("S"), "title": title.strip(), "notes": "", "files": []}
    module["sections"].append(sec)
    return sec

def delete_module(db, module_id):
    db["modules"] = [m for m in db["modules"] if m["id"] != module_id]

def delete_section(module, section_id):
    module["sections"] = [s for s in module["sections"] if s["id"] != section_id]

# -------------------------
# Migration (legacy pages → section notes + files)
# -------------------------
def migrate_pages_to_section_files(db):
    """
    Flattens legacy section.pages[*] into section.files + section.notes.
    Safe to call every run; no-op if already migrated.
    """
    changed = False
    for m in db.get("modules", []):
        for s in m.get("sections", []):
            if "files" not in s:
                s["files"] = []
                changed = True
            if "notes" not in s:
                s["notes"] = ""
                changed = True

            pages = s.get("pages", [])
            if not pages:
                continue

            for p in pages:
                # append page title + content into notes (keeps context)
                ptitle = p.get("title", "Untitled")
                pcontent = p.get("content", "")
                if pcontent:
                    s["notes"] += f"\n\n### {ptitle}\n\n{pcontent}\n"
                    changed = True

                # move files; compute hash to avoid duplicates
                for f in p.get("files", []) or []:
                    fhash = f.get("hash")
                    if not fhash and f.get("path") and os.path.exists(f["path"]):
                        try:
                            with open(f["path"], "rb") as fh:
                                fhash = hashlib.sha256(fh.read()).hexdigest()
                        except Exception:
                            fhash = None
                    if fhash and any(ff.get("hash") == fhash for ff in s["files"]):
                        continue
                    nf = dict(f)
                    nf["hash"] = fhash
                    s["files"].append(nf)
                    changed = True

            # drop legacy pages field
            if "pages" in s:
                s.pop("pages")
                changed = True

    if changed:
        save_db(db)

# -------------------------
# File handling (hash + de-dup)
# -------------------------
def human_size(n):
    try:
        n = float(n)
    except Exception:
        return "—"
    for unit in ["B","KB","MB","GB","TB"]:
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"

def file_sha256(bytes_like):
    return hashlib.sha256(bytes_like).hexdigest()

def save_upload_to_section(section, upload, subdir=""):
    """
    Button-gated upload handler:
    - Reads bytes once (so we can hash and dedupe before writing)
    - Skips if a file with the same content hash already exists in section
    """
    data = upload.read()
    fhash = file_sha256(data)

    # dedupe by content hash
    if any(f.get("hash") == fhash for f in section.get("files", [])):
        return None, "duplicate"

    subpath = UPLOAD_DIR / subdir if subdir else UPLOAD_DIR
    subpath.mkdir(parents=True, exist_ok=True)

    ext = Path(upload.name).suffix
    unique = f"{uuid.uuid4().hex}{ext}"
    dest = subpath / unique
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

# -------------------------
# UI Components
# -------------------------
def header(db):
    st.markdown(f"### {APP_TITLE}")
    st.caption(f"{db['course']['name']} • {db['course']['instructor']}")
    st.caption(f"Last updated: {db['course'].get('updated_at','')}")

def sidebar_mode():
    st.sidebar.subheader("View / Edit")
    mode = st.sidebar.radio(
        "Mode",
        options=["Student (read-only)", "Instructor (edit mode)"],
        index=0,
        help="Use Instructor mode to add or edit content.",
    )
    ok = False
    if mode == "Instructor (edit mode)":
        pwd = st.sidebar.text_input("Passcode", type="password", value="")
        if pwd == DEFAULT_EDIT_PASSCODE:
            st.sidebar.success("Edit mode enabled.")
            ok = True
        elif pwd:
            st.sidebar.error("Incorrect passcode.")
    return mode, ok

def sidebar_backup_restore(db):
    with st.sidebar.expander("Backup / Restore", expanded=False):
        st.write("**Export** a full backup of your database (JSON):")
        st.download_button(
            "Download backup",
            data=json.dumps(db, indent=2, ensure_ascii=False),
            file_name="phy132_backup.json",
            mime="application/json",
            use_container_width=True,
        )
        st.write("**Import** a database (replaces current):")
        up = st.file_uploader("Choose backup JSON", type=["json"], key="restore_uploader")
        if up is not None:
            try:
                newdb = json.loads(up.getvalue().decode("utf-8"))
                if "modules" in newdb and "course" in newdb:
                    save_db(newdb)
                    st.success("Backup imported. Please reload the app.")
                else:
                    st.error("Invalid backup structure.")
            except Exception as e:
                st.error(f"Failed to import: {e}")

def search_box(db):
    q = st.text_input("Search modules, sections, notes, and file names",
                      placeholder="e.g., Kirchhoff, lenses, capacitor…")
    if not q:
        return
    qlow = q.lower()
    results = []
    for m in db["modules"]:
        for s in m.get("sections", []):
            hay_notes = (s.get("notes") or "").lower()
            filenames = " ".join((f.get("name") or "") for f in s.get("files", []))
            hay = f"{m.get('title','')} || {s.get('title','')} || {hay_notes} || {filenames}".lower()
            if qlow in hay:
                results.append((m, s))

    if results:
        st.write(f"**Found {len(results)} result(s):**")
        for m, s in results:
            with st.container(border=True):
                st.markdown(f"**{m['title']} › {s['title']}**")
                preview = (s.get("notes","") or "").strip()
                if preview:
                    st.caption(preview[:240] + ("…" if len(preview) > 240 else ""))
                if st.button("Open", key=f"open-{m['id']}-{s['id']}"):
                    st.session_state["open_ids"] = {"m": m["id"], "s": s["id"]}
                    st.rerun()
    else:
        st.info("No matches.")

def nav_selectors(db):
    # support preselection from search via session_state["open_ids"]
    open_ids = st.session_state.get("open_ids", {})
    modules = db["modules"]

    # module index
    mod_idx_default = 0 if modules else None
    if open_ids:
        for i, m in enumerate(modules):
            if m["id"] == open_ids.get("m"):
                mod_idx_default = i
                break

    mod_titles = [m["title"] for m in modules]
    mod_idx = st.selectbox(
        "Module",
        options=list(range(len(modules))) if modules else [],
        index=mod_idx_default if mod_idx_default is not None and modules else 0,
        format_func=lambda i: mod_titles[i] if modules else "",
        key="module_select",
    ) if modules else None
    module = modules[mod_idx] if mod_idx is not None else None

    sections = module["sections"] if module else []
    # section index
    sec_idx_default = 0 if sections else None
    if open_ids and module:
        for i, s in enumerate(sections):
            if s["id"] == open_ids.get("s"):
                sec_idx_default = i
                break

    sec_titles = [s["title"] for s in sections]
    sec_idx = st.selectbox(
        "Section",
        options=list(range(len(sections))) if sections else [],
        index=sec_idx_default if sec_idx_default is not None and sections else 0,
        format_func=lambda i: sec_titles[i] if sections else "",
        key="section_select",
    ) if sections else None
    section = sections[sec_idx] if sec_idx is not None else None

    # clear open_ids after using them once
    if "open_ids" in st.session_state:
        st.session_state.pop("open_ids", None)

    return module, section

# -------------------------
# View renderer
# -------------------------
def render_section_view(section):
    st.markdown(f"#### {section['title']}")
    # Notes
    if section.get("notes"):
        st.markdown(section["notes"])
    # Files
    if section.get("files"):
        st.markdown("**Files**")
        for f in section["files"]:
            size = human_size(f.get("size", 0))
            col1, col2 = st.columns([3,1])
            with col1:
                st.write(f"• {f['name']}  \n*Uploaded: {f.get('uploaded_at','')} • {size}*")
            with col2:
                try:
                    with open(f["path"], "rb") as fh:
                        st.download_button("Download", data=fh.read(), file_name=f["name"], key=f"dl-{f['path']}")
                except Exception:
                    st.error("Missing file on disk.")

# -------------------------
# Instructor tools (section-level)
# -------------------------
def edit_tools(db, module, section):
    st.divider()
    st.subheader("Instructor Tools")

    with st.expander("Add / Edit Structure", expanded=True):
        cols = st.columns(2)
        with cols[0]:
            st.markdown("**Modules**")
            new_mod = st.text_input("New module title", key="new_mod_title")
            if st.button("Add module", use_container_width=True):
                if new_mod.strip():
                    add_module(db, new_mod)
                    save_db(db)
                    st.rerun()

            if module:
                new_title = st.text_input("Rename selected module", value=module["title"], key=f"rename_mod_{module['id']}")
                if st.button("Save module title", use_container_width=True):
                    module["title"] = new_title.strip() or module["title"]
                    save_db(db)
                    st.rerun()
                if st.button("Delete module", type="primary", use_container_width=True):
                    delete_module(db, module["id"])
                    save_db(db)
                    st.rerun()

        with cols[1]:
            st.markdown("**Sections**")
            if module:
                new_sec = st.text_input("New section title", key="new_sec_title")
                if st.button("Add section", use_container_width=True):
                    if new_sec.strip():
                        add_section(module, new_sec)
                        save_db(db)
                        st.rerun()
                if section:
                    sec_title = st.text_input("Rename selected section", value=section["title"], key=f"rename_sec_{section['id']}")
                    if st.button("Save section title", use_container_width=True):
                        section["title"] = sec_title.strip() or section["title"]
                        save_db(db)
                        st.rerun()
                    if st.button("Delete section", type="primary", use_container_width=True):
                        delete_section(module, section["id"])
                        save_db(db)
                        st.rerun()

    if section:
        with st.expander("Section Notes (Markdown)"):
            notes = st.text_area("Markdown", value=section.get("notes",""), height=260, key=f"sec_notes_{section['id']}")
            if st.button("Save notes", use_container_width=True):
                section["notes"] = notes
                save_db(db)
                st.success("Saved.")

        with st.expander("Manage Section Files"):
            # uploader reset key per section to avoid repeated processing on rerun
            uk_key = f"upload_key_{section['id']}"
            if uk_key not in st.session_state:
                st.session_state[uk_key] = 0

            uploader_key = f"uploader_{section['id']}_{st.session_state[uk_key]}"
            uploads = st.file_uploader("Select files", accept_multiple_files=True, key=uploader_key)

            # Only persist when user clicks the button (prevents loops on rerun)
            if st.button("Add files to section", use_container_width=True):
                added, skipped = 0, 0
                if uploads:
                    for up in uploads:
                        meta, status = save_upload_to_section(section, up, subdir=section["id"])
                        if status == "saved":
                            added += 1
                        else:
                            skipped += 1
                    save_db(db)
                    st.success(f"Added {added} file(s). Skipped {skipped} duplicate(s).")
                else:
                    st.info("No files selected.")
                # reset uploader (new key) so it doesn't re-submit on rerun
                st.session_state[uk_key] += 1
                st.rerun()

            # Existing attachments with remove buttons
            if section.get("files"):
                st.write("Existing files:")
                keep = []
                changed = False
                for f in section["files"]:
                    col1, col2, col3 = st.columns([5,2,1])
                    with col1:
                        st.write(f"{f['name']}  \n*{human_size(f.get('size',0))} • uploaded {f.get('uploaded_at','')}*")
                    with col2:
                        try:
                            with open(f["path"], "rb") as fh:
                                st.download_button("Download", data=fh.read(), file_name=f["name"], key=f"dl2-{f['path']}")
                        except Exception:
                            st.error("Missing file on disk.")
                    with col3:
                        if st.button("❌", key=f"rm-{f['path']}"):
                            try:
                                if os.path.exists(f["path"]):
                                    os.remove(f["path"])
                            except Exception:
                                pass
                            changed = True
                        else:
                            keep.append(f)
                if changed:
                    section["files"] = keep
                    save_db(db)
                    st.rerun()

    with st.expander("Course Footer / Info"):
        c = db["course"]
        name = st.text_input("Course name", value=c.get("name",""))
        instr = st.text_input("Instructor line", value=c.get("instructor",""))
        if st.button("Save course info"):
            c["name"] = name.strip() or c["name"]
            c["instructor"] = instr.strip() or c["instructor"]
            save_db(db)
            st.success("Saved.")

# -------------------------
# Main App
# -------------------------
def main():
    st.set_page_config(page_title="PHY 132 Local Hub", layout="wide")

    db = load_db()
    # Migrate legacy structures if present
    migrate_pages_to_section_files(db)

    header(db)
    mode, can_edit = sidebar_mode()
    sidebar_backup_restore(db)

    st.markdown("---")
    left, right = st.columns([2,1], vertical_alignment="top")

    # Left: navigation + section view
    with left:
        with st.expander("Quick Search", expanded=False):
            search_box(db)

        st.subheader("Browse")
        module, section = nav_selectors(db)

        if section:
            render_section_view(section)
        else:
            st.info("Select a module and section to view content.")

    # Right: instructor tools (or info panel)
    with right:
        if mode.startswith("Instructor") and can_edit:
            edit_tools(db, module, section)
        else:
            st.subheader("About this Hub")
            st.write(
                "This offline hub keeps PHY 132 materials accessible during outages. "
                "Use the navigation to browse modules. When connectivity returns, you can export a backup JSON."
            )
            st.markdown(
                "- **Read-only for students.**\n"
                "- **Instructor mode** (sidebar) lets you add/edit content.\n"
                "- **Attachments** are stored locally in `uploads/`."
            )
            st.caption("Tip: press **?** in Streamlit for keyboard shortcuts.")

    st.markdown("---")
    st.caption("© Eastern Kentucky University • PHY 132 • Local Course Hub")

if __name__ == "__main__":
    main()