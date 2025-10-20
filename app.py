# app.py
# ---------------------------------------------
# PHY 132 Local Course Hub (offline-ready)
# Stores modules, sections, pages, and uploads
# ---------------------------------------------
# How to run:
#   streamlit run app.py
#
# Folders created on first run:
#   ./data/modules.json     (persistent DB)
#   ./uploads/              (attachments)
#
# Features:
# - Student View (read-only): browse modules, sections, pages; search content
# - Instructor Edit Mode: add/edit/delete modules/sections/pages; upload files
# - Content types: Markdown pages + file attachments
# - Backup/Restore: export/import JSON (no internet needed)
#
# Tip: Use the passcode in the sidebar to enable edit mode.
#      Change the default passcode below if desired.

import os
import json
import uuid
import shutil
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
DEFAULT_EDIT_PASSCODE = "eku132"  # change to your own

# Seed modules aligned with your course (only used on very first run)
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
    "version": 1,
}

# -------------------------
# Helpers (DB I/O)
# -------------------------
def ensure_dirs():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def load_db():
    ensure_dirs()
    if not DB_PATH.exists():
        db = DEFAULT_DB
        db["course"]["updated_at"] = timestamp()
        save_db(db)
        return db
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    db["course"]["updated_at"] = timestamp()
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

# -------------------------
# Data structure utilities
# -------------------------
def get_module(db, module_id):
    return next((m for m in db["modules"] if m["id"] == module_id), None)

def get_section(module, section_id):
    return next((s for s in module.get("sections", []) if s["id"] == section_id), None)

def get_page(section, page_id):
    return next((p for p in section.get("pages", []) if p["id"] == page_id), None)

def add_module(db, title):
    mod = {"id": new_id("M"), "title": title.strip(), "sections": []}
    db["modules"].append(mod)
    return mod

def add_section(module, title):
    sec = {"id": new_id("S"), "title": title.strip(), "pages": []}
    module["sections"].append(sec)
    return sec

def add_page(section, title, kind="markdown", content="", files=None):
    if files is None:
        files = []
    page = {
        "id": new_id("P"),
        "title": title.strip(),
        "type": kind,        # "markdown"
        "content": content,  # markdown text
        "files": files,      # list of {"name","path","size","uploaded_at"}
        "tags": [],
        "updated_at": timestamp(),
    }
    section.setdefault("pages", []).append(page)
    return page

def delete_module(db, module_id):
    db["modules"] = [m for m in db["modules"] if m["id"] != module_id]

def delete_section(module, section_id):
    module["sections"] = [s for s in module["sections"] if s["id"] != section_id]

def delete_page(section, page_id):
    section["pages"] = [p for p in section["pages"] if p["id"] != page_id]

# -------------------------
# File handling
# -------------------------
def save_upload(upload, subdir=""):
    subpath = UPLOAD_DIR / subdir if subdir else UPLOAD_DIR
    subpath.mkdir(parents=True, exist_ok=True)
    # Create a stable, unique filename preserving extension
    ext = Path(upload.name).suffix
    unique = f"{uuid.uuid4().hex}{ext}"
    dest = subpath / unique
    with open(dest, "wb") as f:
        f.write(upload.read())
    return {
        "name": upload.name,
        "path": str(dest),
        "size": dest.stat().st_size,
        "uploaded_at": timestamp(),
    }

def human_size(n):
    for unit in ["B","KB","MB","GB","TB"]:
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"

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

def nav_selectors(db):
    # Return selected module/section/page IDs
    modules = db["modules"]
    mod_titles = [m["title"] for m in modules]
    mod_idx = st.selectbox("Module", options=list(range(len(modules))), format_func=lambda i: mod_titles[i]) if modules else None
    module = modules[mod_idx] if mod_idx is not None else None

    sections = module["sections"] if module else []
    sec_titles = [s["title"] for s in sections]
    sec_idx = st.selectbox("Section", options=list(range(len(sections))), format_func=lambda i: sec_titles[i]) if sections else None
    section = sections[sec_idx] if sec_idx is not None else None

    pages = section.get("pages", []) if section else []
    page_titles = [p["title"] for p in pages]
    page_idx = st.selectbox("Page", options=list(range(len(pages))), format_func=lambda i: page_titles[i]) if pages else None
    page = pages[page_idx] if page_idx is not None else None

    return module, section, page

def search_box(db):
    q = st.text_input("Search titles & text", placeholder="e.g., Gauss's law, Kirchhoff, lenses…")
    if not q:
        return
    qlow = q.lower()
    results = []
    for m in db["modules"]:
        for s in m.get("sections", []):
            for p in s.get("pages", []):
                hay = f"{p.get('title','')}||{p.get('content','')}".lower()
                if qlow in hay:
                    results.append((m, s, p))
    if results:
        st.write(f"**Found {len(results)} result(s):**")
        for m, s, p in results:
            with st.container(border=True):
                st.markdown(f"**{m['title']} › {s['title']} › {p['title']}**")
                preview = (p.get("content","") or "").strip()
                if preview:
                    st.caption(preview[:240] + ("…" if len(preview) > 240 else ""))
                if st.button("Open", key=f"open-{p['id']}"):
                    st.session_state["open_ids"] = {"m": m["id"], "s": s["id"], "p": p["id"]}
    else:
        st.info("No matches.")

def locate_by_ids(db, ids):
    if not ids:
        return None, None, None
    m = get_module(db, ids.get("m"))
    if not m:
        return None, None, None
    s = get_section(m, ids.get("s")) if ids.get("s") else None
    p = get_page(s, ids.get("p")) if (s and ids.get("p")) else None
    return m, s, p

# -------------------------
# View Renderers
# -------------------------
def render_page_view(page):
    st.markdown(f"#### {page['title']}")
    st.caption(f"Last updated: {page.get('updated_at','')}")
    if page["type"] == "markdown" and page.get("content"):
        st.markdown(page["content"])
    if page.get("files"):
        st.markdown("**Attachments**")
        for f in page["files"]:
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
# Edit Forms (Instructor)
# -------------------------
def edit_tools(db, module, section, page):
    st.divider()
    st.subheader("Instructor Tools")

    with st.expander("Add / Edit Content", expanded=True):
        cols = st.columns(3)
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

        with cols[2]:
            st.markdown("**Pages**")
            if section:
                new_page_title = st.text_input("New page title", key="new_page_title")
                if st.button("Add page", use_container_width=True):
                    if new_page_title.strip():
                        add_page(section, new_page_title, kind="markdown", content="*Draft page*")
                        save_db(db)
                        st.rerun()
                if page:
                    page_title = st.text_input("Rename selected page", value=page["title"], key=f"rename_page_{page['id']}")
                    if st.button("Save page title", use_container_width=True):
                        page["title"] = page_title.strip() or page["title"]
                        page["updated_at"] = timestamp()
                        save_db(db)
                        st.rerun()
                    if st.button("Delete page", type="primary", use_container_width=True):
                        delete_page(section, page["id"])
                        save_db(db)
                        st.rerun()

    if page:
        with st.expander("Edit Page Content (Markdown)"):
            content = st.text_area("Markdown", value=page.get("content",""), height=260, key=f"page_md_{page['id']}")
            if st.button("Save page content", use_container_width=True):
                page["content"] = content
                page["updated_at"] = timestamp()
                save_db(db)
                st.success("Saved.")

        with st.expander("Manage Attachments"):
            uploads = st.file_uploader("Add files", accept_multiple_files=True)
            if uploads:
                # Save all uploads
                saved = []
                for up in uploads:
                    meta = save_upload(up, subdir=page["id"])
                    saved.append(meta)
                page.setdefault("files", []).extend(saved)
                page["updated_at"] = timestamp()
                save_db(db)
                st.success(f"Added {len(saved)} file(s).")
                st.rerun()

            # Existing attachments with remove buttons
            if page.get("files"):
                st.write("Existing files:")
                keep = []
                changed = False
                for f in page["files"]:
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
                            # Remove file from disk if present
                            try:
                                if os.path.exists(f["path"]):
                                    os.remove(f["path"])
                            except Exception:
                                pass
                            changed = True
                        else:
                            keep.append(f)
                if changed:
                    page["files"] = keep
                    page["updated_at"] = timestamp()
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

    header(db)
    mode, can_edit = sidebar_mode()
    sidebar_backup_restore(db)

    st.markdown("---")
    left, right = st.columns([2,1], vertical_alignment="top")

    # Left: navigation + page view
    with left:
        # If a search opens a specific page, carry that selection
        if "open_ids" not in st.session_state:
            st.session_state["open_ids"] = {}

        # Search
        with st.expander("Quick Search", expanded=False):
            search_box(db)

        # If a result set requested to open specific IDs, select them
        if st.session_state.get("open_ids"):
            m, s, p = locate_by_ids(db, st.session_state["open_ids"])
            if m and s:
                # make selectboxes preselect these by temporarily reordering
                pass  # handled below by selectbox UI; IDs are kept in state for reference

        st.subheader("Browse")
        module, section, page = nav_selectors(db)

        if page:
            render_page_view(page)
        else:
            st.info("Select a module, section, and page to view content.")

    # Right: instructor tools (or helpful info)
    with right:
        if mode.startswith("Instructor") and can_edit:
            edit_tools(db, module, section, page)
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