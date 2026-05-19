# Glass Premium Dark Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current light sidebar UI in `app.py` with a dark glassmorphism theme — `#09090e` background with gradient orbs, a sticky 52px top nav bar (replacing the sidebar), and dark-glass styling on all cards and form inputs.

**Architecture:** All changes are in `lb_migration_platform_ui/app.py`. There are four edit sites: (1) the CSS `st.markdown` block, (2) `st.set_page_config` `initial_sidebar_state`, (3) the sidebar navigation block replaced by query-params routing + top-nav HTML injection, (4) hardcoded light-colour inline HTML strings updated to dark-theme equivalents.

**Tech Stack:** Streamlit, CSS (glassmorphism, `backdrop-filter`), Google Fonts (Inter, JetBrains Mono), `st.query_params` for URL-based navigation, base64-encoded PNG logo.

---

## File Map

| File | Change |
|------|--------|
| `lb_migration_platform_ui/app.py:148-153` | Change `initial_sidebar_state` to `"collapsed"` |
| `lb_migration_platform_ui/app.py:159-341` | Replace entire CSS `st.markdown` block with dark glass theme CSS |
| `lb_migration_platform_ui/app.py:1387-1451` | Replace sidebar block + page-header block with query-params nav + top-nav HTML |
| `lb_migration_platform_ui/app.py` (scattered) | Update ~15 inline HTML fragments with hardcoded light colours |

---

### Task 1: Dark Glass CSS block

**Files:**
- Modify: `lb_migration_platform_ui/app.py:159-341`

No automated tests for pure CSS. Visual verification: run `streamlit run app.py` and confirm dark background renders.

- [ ] **Step 1: Replace the CSS block**

Find the block that starts at line 159:
```python
st.markdown("""
<style>
/* ── Fonts & base ─────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
```
…and ends at line 341:
```python
</style>
""", unsafe_allow_html=True)
```

Replace the **entire block** (from the opening `st.markdown("""` to the closing `""", unsafe_allow_html=True)`) with the block below. The old block is ~180 lines; the new block is ~320 lines. Replace it exactly — do not merge or keep any old CSS rules.

```python
# ── base64-encode logo once at startup ───────────────────────────────────────
import base64 as _b64
_LOGO_B64 = ""
_logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
if os.path.exists(_logo_path):
    with open(_logo_path, "rb") as _lf:
        _LOGO_B64 = _b64.b64encode(_lf.read()).decode()

st.markdown(f"""
<style>
/* ── Google Fonts ─────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── CSS variables ────────────────────────────────────────────────────────── */
:root {{
    --bg:          #09090e;
    --orange:      #FF3621;
    --orange-dim:  rgba(255,54,33,0.15);
    --indigo:      #6366f1;
    --cyan:        #06b6d4;
    --glass-bg:    rgba(255,255,255,0.03);
    --glass-bdr:   rgba(255,255,255,0.08);
    --text-pri:    #f1f5f9;
    --text-muted:  #94a3b8;
    --nav-h:       52px;
}}

/* ── Base ─────────────────────────────────────────────────────────────────── */
html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
    color: var(--text-pri);
}}

/* ── App background ───────────────────────────────────────────────────────── */
.stApp {{
    background-color: var(--bg) !important;
}}

/* Radial gradient orbs rendered on the app root */
.stApp::before {{
    content: '';
    position: fixed; inset: 0; pointer-events: none; z-index: 0;
    background:
        radial-gradient(ellipse 700px 500px at 15% 10%,  rgba(255,54,33,0.10)  0%, transparent 70%),
        radial-gradient(ellipse 600px 500px at 85% 20%,  rgba(99,102,241,0.08) 0%, transparent 70%),
        radial-gradient(ellipse 500px 400px at 50% 85%,  rgba(6,182,212,0.06)  0%, transparent 70%);
}}

/* ── Hide Streamlit chrome ────────────────────────────────────────────────── */
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{
    padding-top: calc(var(--nav-h) + 1.75rem) !important;
    padding-bottom: 3rem;
    max-width: 1100px;
    position: relative; z-index: 1;
}}

/* ── Hide sidebar entirely ────────────────────────────────────────────────── */
section[data-testid="stSidebar"],
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"] {{
    display: none !important;
    visibility: hidden !important;
}}

/* ── Top nav (injected HTML — fixed position) ─────────────────────────────── */
#sb-nav {{
    position: fixed; top: 0; left: 0; right: 0;
    height: var(--nav-h);
    background: rgba(9,9,14,0.88);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--glass-bdr);
    z-index: 9999;
    display: flex; align-items: center;
    padding: 0 24px; gap: 8px;
    font-family: 'Inter', sans-serif;
}}
#sb-nav .sb-logo {{
    display: flex; align-items: center; gap: 10px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 999px;
    padding: 4px 14px 4px 6px;
    margin-right: 16px;
    text-decoration: none; cursor: pointer;
}}
#sb-nav .sb-logo img {{ height: 28px; width: auto; border-radius: 4px; }}
#sb-nav .sb-logo span {{
    font-size: 13px; font-weight: 700;
    color: #fff; letter-spacing: 0.02em;
}}
#sb-nav .sb-divider {{
    width: 1px; height: 20px;
    background: var(--glass-bdr); margin: 0 8px;
}}
#sb-nav .sb-links {{ display: flex; align-items: center; gap: 2px; }}
#sb-nav .sb-link {{
    padding: 6px 14px; border-radius: 8px;
    font-size: 13px; font-weight: 500;
    color: var(--text-muted);
    text-decoration: none; cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s;
}}
#sb-nav .sb-link:hover {{
    color: var(--text-pri);
    background: rgba(255,255,255,0.05);
}}
#sb-nav .sb-link.active {{
    color: var(--orange);
    background: rgba(255,54,33,0.08);
    border-color: rgba(255,54,33,0.2);
}}
#sb-nav .sb-spacer {{ flex: 1; }}
#sb-nav .sb-badge {{
    font-size: 11px; font-weight: 600;
    color: var(--text-muted);
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--glass-bdr);
    border-radius: 6px; padding: 3px 9px;
    letter-spacing: 0.03em;
}}

/* ── fadeUp animation ─────────────────────────────────────────────────────── */
@keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(16px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}

/* ── Page header ──────────────────────────────────────────────────────────── */
.page-hdr {{
    display: flex; align-items: flex-start; gap: 0.9rem;
    border-bottom: 1px solid var(--glass-bdr);
    padding-bottom: 1.25rem; margin-bottom: 2rem;
    animation: fadeUp 0.4s ease both;
}}
.page-hdr-icon {{
    width: 44px; height: 44px; border-radius: 10px;
    background: var(--glass-bg);
    border: 1px solid var(--glass-bdr);
    display: flex; align-items: center;
    justify-content: center; font-size: 1.2rem; flex-shrink: 0;
}}
.page-hdr h1 {{
    font-size: 1.45rem; font-weight: 800; color: #fff;
    margin: 0 0 0.1rem; letter-spacing: -0.025em; line-height: 1.2;
}}
.page-hdr p {{ color: var(--text-muted); font-size: 0.82rem; margin: 0; }}

/* ── Cards ────────────────────────────────────────────────────────────────── */
.card {{
    background: var(--glass-bg);
    border: 1px solid var(--glass-bdr);
    border-radius: 14px; padding: 1.4rem 1.6rem;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    animation: fadeUp 0.45s ease both;
}}
.card-title {{
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--text-muted); margin-bottom: 1rem;
    display: flex; align-items: center; gap: 0.4rem;
}}

/* ── Step indicator ───────────────────────────────────────────────────────── */
.step-num {{
    width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.78rem; font-weight: 700;
    background: var(--orange); color: white; margin-right: 0.45rem;
}}
.step-num.teal {{ background: #0f766e; }}

/* ── Extension tags ───────────────────────────────────────────────────────── */
.ext-wrap {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 0.5rem; }}
.ext-tag {{
    background: rgba(255,255,255,0.04); color: var(--text-muted);
    border: 1px solid var(--glass-bdr); border-radius: 4px;
    padding: 2px 7px; font-size: 0.72rem; font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
}}
.ext-tag.teal {{ background: rgba(6,182,212,0.08); color: #67e8f9; border-color: rgba(6,182,212,0.2); }}

/* ── Primary buttons ──────────────────────────────────────────────────────── */
div[data-testid="stButton"] button {{
    background: var(--orange) !important; color: #fff !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 0.92rem !important;
    padding: 0.6rem 2rem !important;
    box-shadow: 0 0 20px rgba(255,54,33,0.25) !important;
    transition: all 0.15s ease !important;
}}
div[data-testid="stButton"] button:hover {{
    background: #e8301d !important;
    box-shadow: 0 0 32px rgba(255,54,33,0.4) !important;
    transform: translateY(-1px) !important;
}}
div[data-testid="stButton"] button:disabled {{
    background: rgba(255,255,255,0.06) !important;
    color: var(--text-muted) !important;
    box-shadow: none !important; transform: none !important;
}}

/* ── Metric cards ─────────────────────────────────────────────────────────── */
.metric-card {{
    background: var(--glass-bg);
    border: 1px solid var(--glass-bdr); border-radius: 14px;
    padding: 1.25rem 1rem; text-align: center;
    backdrop-filter: blur(12px);
    animation: fadeUp 0.5s ease both;
}}
.metric-icon {{ font-size: 1.4rem; margin-bottom: 0.4rem; }}
.metric-val {{ font-size: 2rem; font-weight: 800; line-height: 1; color: #fff; font-family: 'JetBrains Mono', monospace; }}
.metric-lbl {{
    font-size: 0.68rem; font-weight: 700; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 0.07em; margin-top: 0.35rem;
}}

/* ── Results header ───────────────────────────────────────────────────────── */
.results-header {{ display: flex; align-items: center; margin-bottom: 1.25rem; }}
.results-title {{
    font-size: 1.1rem; font-weight: 700; color: #fff;
    display: flex; align-items: center; gap: 0.5rem;
}}
.success-pill {{
    background: rgba(34,197,94,0.12); color: #4ade80;
    border: 1px solid rgba(34,197,94,0.2);
    border-radius: 20px; padding: 2px 10px;
    font-size: 0.73rem; font-weight: 600;
}}

/* ── Section divider ──────────────────────────────────────────────────────── */
.section-sep {{ border: none; border-top: 1px solid var(--glass-bdr); margin: 1.75rem 0; }}

/* ── File tree / output block ─────────────────────────────────────────────── */
.file-tree {{
    background: rgba(0,0,0,0.5); color: #e2e8f0; border-radius: 10px;
    padding: 1rem 1.25rem; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
    line-height: 1.7; max-height: 360px; overflow-y: auto;
    width: 100%; overflow-x: auto; white-space: nowrap; word-break: break-word;
    border: 1px solid var(--glass-bdr);
}}
.file-tree .dir  {{ color: var(--orange); font-weight: 600; }}
.file-tree .file {{ color: #86efac; }}
.file-tree .meta {{ color: #475569; }}

.output-block {{
    background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.06); border-radius: 0.85rem;
    padding: 0.85rem; max-height: 42vh; overflow-y: auto;
    white-space: pre-wrap; word-break: break-word;
    color: var(--text-pri); font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
}}

/* ── Info box ─────────────────────────────────────────────────────────────── */
.info-box {{
    background: var(--glass-bg); border: 1px solid var(--glass-bdr); border-radius: 10px;
    padding: 0.85rem 1.1rem; margin-top: 0.5rem;
}}
.info-box strong {{ color: #fff; }}
.info-box p {{ color: var(--text-muted); font-size: 0.85rem; margin: 0.2rem 0 0; }}

/* ── Dark Streamlit widgets ───────────────────────────────────────────────── */
/* selectbox, text_input, text_area, number_input */
.stSelectbox > div > div,
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {{
    background: rgba(255,255,255,0.04) !important;
    border-color: var(--glass-bdr) !important;
    color: #f1f5f9 !important;
    border-radius: 8px !important;
}}
.stSelectbox > div > div:focus-within,
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {{
    border-color: rgba(255,54,33,0.4) !important;
    box-shadow: 0 0 0 1px rgba(255,54,33,0.25) !important;
}}
/* Selectbox dropdown option text */
.stSelectbox div[data-baseweb="select"] span {{ color: #f1f5f9 !important; }}
/* Selectbox dropdown arrow */
.stSelectbox svg {{ fill: var(--text-muted) !important; }}

/* radio labels */
.stRadio label {{ color: var(--text-pri) !important; }}

/* file uploader */
div[data-testid="stFileUploader"] {{
    background: var(--glass-bg) !important;
    border-color: var(--glass-bdr) !important;
    border-radius: 10px !important;
}}
div[data-testid="stFileUploader"] span {{ color: var(--text-muted) !important; }}

/* expander */
.streamlit-expanderHeader {{
    background: var(--glass-bg) !important;
    color: var(--text-pri) !important;
    border-color: var(--glass-bdr) !important;
    border-radius: 8px !important;
}}
.streamlit-expanderContent {{
    background: rgba(0,0,0,0.2) !important;
    border-color: var(--glass-bdr) !important;
}}

/* checkboxes */
.stCheckbox label {{ color: var(--text-pri) !important; }}

/* st.caption */
.stCaption {{ color: var(--text-muted) !important; }}

/* st.tabs */
div[data-testid="stTabs"] button {{
    color: var(--text-muted) !important;
    background: transparent !important;
    border-color: transparent !important;
}}
div[data-testid="stTabs"] button[aria-selected="true"] {{
    color: var(--text-pri) !important;
    border-bottom-color: var(--orange) !important;
}}

/* st.dataframe / st.table */
.stDataFrame {{ filter: invert(0.85) hue-rotate(180deg); }}

/* st.success / st.error / st.warning / st.info */
div[data-testid="stAlert"] {{ border-radius: 10px !important; }}

/* placeholder text */
input::placeholder, textarea::placeholder {{ color: #475569 !important; }}

/* general text in app */
p, li, span, label {{ color: var(--text-pri); }}
h1, h2, h3, h4, h5, h6 {{ color: #fff; }}
strong {{ color: #fff; }}

/* horizontal rule */
hr {{ border-color: var(--glass-bdr) !important; }}
</style>
""", unsafe_allow_html=True)
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
git add lb_migration_platform_ui/app.py
git commit -m "feat: dark glass theme — CSS foundation + widget overrides"
```

---

### Task 2: Navigation — sidebar → top nav + query_params routing

**Files:**
- Modify: `lb_migration_platform_ui/app.py:148-153` (set_page_config)
- Modify: `lb_migration_platform_ui/app.py:1387-1451` (sidebar block + page header)

- [ ] **Step 1: Change `initial_sidebar_state` in `st.set_page_config`**

Find (around line 148):
```python
st.set_page_config(
    page_title="SyrenBridge — Migration Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
```

Replace with:
```python
st.set_page_config(
    page_title="SyrenBridge — Migration Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
```

- [ ] **Step 2: Replace sidebar block + page header block**

Find the block starting at (around line 1383):
```python
# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
```
…through to and including line 1451:
```python
""", unsafe_allow_html=True)
```
(the closing of the `st.markdown` for the page header div that renders `page-hdr`).

Replace the **entire block** from the `# SIDEBAR NAVIGATION` comment through the closing `""", unsafe_allow_html=True)` of the page header with:

```python
# ══════════════════════════════════════════════════════════════════════════════
# TOP NAV + ROUTING
# ══════════════════════════════════════════════════════════════════════════════

_PAGES = ["Get Started", "Analyzer", "Transpiler", "Settings"]
selected_page = st.query_params.get("page", "Get Started")
if selected_page not in _PAGES:
    selected_page = "Get Started"

_logo_src = f"data:image/png;base64,{_LOGO_B64}" if _LOGO_B64 else ""
_logo_img = f'<img src="{_logo_src}" alt="Syren">' if _logo_src else ""

def _nav_link(label: str, page: str, active: str) -> str:
    cls = "sb-link active" if page == active else "sb-link"
    return (
        f'<a class="{cls}" href="?page={page}" target="_self">{label}</a>'
    )

_nav_html = f"""
<div id="sb-nav">
    <a class="sb-logo" href="?page=Get+Started" target="_self">
        {_logo_img}
        <span>SyrenBridge</span>
    </a>
    <div class="sb-divider"></div>
    <div class="sb-links">
        {_nav_link("Home", "Get Started", selected_page)}
        {_nav_link("Analyser", "Analyzer", selected_page)}
        {_nav_link("Transpiler", "Transpiler", selected_page)}
        {_nav_link("Settings", "Settings", selected_page)}
    </div>
    <div class="sb-spacer"></div>
    <span class="sb-badge">⚡ 13 Dialects</span>
</div>
"""
st.markdown(_nav_html, unsafe_allow_html=True)


# ── Page header renderer ──────────────────────────────────────────────────────
_PAGE_META = {
    "Get Started": ("📚", "Get Started", "Overview, capabilities, and how to use SyrenBridge"),
    "Analyzer":    ("🔍", "Code Analyzer", "Analyze legacy source code for migration readiness"),
    "Transpiler":  ("⚡", "Code Transpiler", "Convert source code to Databricks-compatible output"),
    "Settings":    ("⚙️", "Settings", "Configure Databricks workspace credentials"),
}
_icon, _title, _subtitle = _PAGE_META[selected_page]
st.markdown(f"""
<div class="page-hdr">
    <div class="page-hdr-icon">{_icon}</div>
    <div>
        <h1>{_title}</h1>
        <p>{_subtitle} &nbsp;·&nbsp; SyrenBridge by Syren Cloud</p>
    </div>
</div>
""", unsafe_allow_html=True)
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
git add lb_migration_platform_ui/app.py
git commit -m "feat: dark glass theme — replace sidebar with top nav + query_params routing"
```

---

### Task 3: Fix inline HTML — Get Started page

**Files:**
- Modify: `lb_migration_platform_ui/app.py` (lines ~1461–1622)

All inline `style=""` HTML strings in the Get Started block use light colours (`#475569`, `#f8fafc`, `#e2e8f0`, `#0f172a`, `#ffffff`, `#f8fafc`). Replace them with dark-theme equivalents.

- [ ] **Step 1: Update intro paragraph colours**

Find (around line 1461):
```python
    st.markdown("""
    <div style="max-width:720px;margin-bottom:2rem;">
        <p style="color:#475569;font-size:0.95rem;line-height:1.7;margin:0;">
```
Replace the `color:#475569` with `color:#94a3b8`:
```python
    st.markdown("""
    <div style="max-width:720px;margin-bottom:2rem;">
        <p style="color:#94a3b8;font-size:0.95rem;line-height:1.7;margin:0;">
```

- [ ] **Step 2: Update Quick Start card background and dividers**

Find (around line 1473):
```python
    st.markdown("""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;
                padding:1.5rem 1.75rem;margin-bottom:2rem;">
```
Replace with:
```python
    st.markdown("""
    <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:12px;
                padding:1.5rem 1.75rem;margin-bottom:2rem;backdrop-filter:blur(12px);">
```

Find inside that block:
```python
                <div style="font-weight:700;color:#0f172a;margin-bottom:0.3rem;font-size:0.95rem;">
                    🔍 Analyze
                </div>
                <div style="font-size:0.85rem;color:#64748b;line-height:1.6;">
```
Replace all three step titles' `color:#0f172a` → `color:#f1f5f9` and step body text `color:#64748b` → `color:#94a3b8`. There are 3 step blocks — do all of them. Also update the two dividers from `border-left:1px solid #e2e8f0` → `border-left:1px solid rgba(255,255,255,0.08)`.

The corrected Quick Start block in full:
```python
    st.markdown("""
    <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:12px;
                padding:1.5rem 1.75rem;margin-bottom:2rem;backdrop-filter:blur(12px);">
        <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.1em;
                    text-transform:uppercase;margin-bottom:1.1rem;">Quick Start</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.25rem;">
            <div>
                <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.08em;
                            text-transform:uppercase;margin-bottom:0.3rem;">Step 1</div>
                <div style="font-weight:700;color:#f1f5f9;margin-bottom:0.3rem;font-size:0.95rem;">
                    🔍 Analyze
                </div>
                <div style="font-size:0.85rem;color:#94a3b8;line-height:1.6;">
                    Select your source technology, upload source files or use Databricks workspace folder files, and get a
                    migration-readiness report — object inventory, function usage, SQL category breakdown.
                </div>
            </div>
            <div style="border-left:1px solid rgba(255,255,255,0.08);padding-left:1.25rem;">
                <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.08em;
                            text-transform:uppercase;margin-bottom:0.3rem;">Step 2</div>
                <div style="font-weight:700;color:#f1f5f9;margin-bottom:0.3rem;font-size:0.95rem;">
                    ⚡ Transpile
                </div>
                <div style="font-size:0.85rem;color:#94a3b8;line-height:1.6;">
                    Select your source dialect, upload files either locally or from your Databricks workspace, and download Databricks-compatible
                    output — SQL, PySpark notebooks, or Workflow JSON or you can write directly to your workspace folders.
                </div>
            </div>
            <div style="border-left:1px solid rgba(255,255,255,0.08);padding-left:1.25rem;">
                <div style="font-size:0.7rem;font-weight:700;color:#94a3b8;letter-spacing:0.08em;
                            text-transform:uppercase;margin-bottom:0.3rem;">First time?</div>
                <div style="font-weight:700;color:#f1f5f9;margin-bottom:0.3rem;font-size:0.95rem;">
                    ⚙️ Configure
                </div>
                <div style="font-size:0.85rem;color:#94a3b8;line-height:1.6;">
                    If running locally, go to <strong>Settings</strong> and enter your Databricks
                    workspace URL and token. On Databricks Apps this is automatic.
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
```

- [ ] **Step 3: Update dialect table colours**

Find the `gs_table_rows` loop (around line 1538):
```python
    gs_table_rows = ""
    for i, (dialect, engine, output, exts) in enumerate(dialect_rows):
        bg = "#ffffff" if i % 2 == 0 else "#f8fafc"
        gs_table_rows += f"""
        <tr style="background:{bg};">
            <td style="padding:0.55rem 0.85rem;font-weight:600;color:#0f172a;font-size:0.87rem;">{dialect}</td>
            <td style="padding:0.55rem 0.85rem;color:#475569;font-size:0.84rem;">{engine}</td>
            <td style="padding:0.55rem 0.85rem;color:#475569;font-size:0.84rem;">{output}</td>
            <td style="padding:0.55rem 0.85rem;color:#94a3b8;font-size:0.78rem;font-family:monospace;">{exts}</td>
        </tr>"""
```

Replace with:
```python
    gs_table_rows = ""
    for i, (dialect, engine, output, exts) in enumerate(dialect_rows):
        bg = "rgba(255,255,255,0.03)" if i % 2 == 0 else "rgba(255,255,255,0.015)"
        gs_table_rows += f"""
        <tr style="background:{bg};">
            <td style="padding:0.55rem 0.85rem;font-weight:600;color:#f1f5f9;font-size:0.87rem;">{dialect}</td>
            <td style="padding:0.55rem 0.85rem;color:#94a3b8;font-size:0.84rem;">{engine}</td>
            <td style="padding:0.55rem 0.85rem;color:#94a3b8;font-size:0.84rem;">{output}</td>
            <td style="padding:0.55rem 0.85rem;color:#64748b;font-size:0.78rem;font-family:monospace;">{exts}</td>
        </tr>"""
```

Also find the table wrapper (around line 1549):
```python
    st.markdown(f"""
    <div style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:2rem;">
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:#f1f5f9;border-bottom:1px solid #e2e8f0;">
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">Dialect</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">Engine</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">Output</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">File Types</th>
                </tr>
            </thead>
            <tbody>{gs_table_rows}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
```

Replace with:
```python
    st.markdown(f"""
    <div style="border:1px solid rgba(255,255,255,0.08);border-radius:10px;overflow:hidden;margin-bottom:2rem;backdrop-filter:blur(12px);">
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:rgba(255,255,255,0.05);border-bottom:1px solid rgba(255,255,255,0.08);">
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">Dialect</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">Engine</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">Output</th>
                    <th style="padding:0.6rem 0.85rem;text-align:left;font-size:0.68rem;
                               font-weight:700;letter-spacing:0.08em;color:#64748b;text-transform:uppercase;">File Types</th>
                </tr>
            </thead>
            <tbody>{gs_table_rows}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
```

- [ ] **Step 4: Update tech category cards (SQL / ETL / Code)**

Find the `_tech_list` helper and the three `with gs_a1/gs_a2/gs_a3` blocks (around line 1580). The `_tech_list` function returns `li` tags with `color:#475569`. Update:

```python
    def _tech_list(techs):
        return "".join(
            f'<li style="padding:0.1rem 0;color:#94a3b8;font-size:0.85rem;">{t}</li>'
            for t in techs
        )
```

Find each of the three `st.markdown` calls inside `with gs_a1/gs_a2/gs_a3` that look like:
```python
        st.markdown(f"""
        <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:1rem 1.25rem;">
```

Replace `background:#fff;border:1px solid #e2e8f0` → `background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08)` for all three cards.

- [ ] **Step 5: Update PySpark note banner**

Find (around line 1613):
```python
    st.markdown(
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
        'padding:0.8rem 1.1rem;font-size:0.86rem;color:#475569;">'
        '💡 <strong style="color:#0f172a;">PySpark &amp; Spark Classic → Serverless</strong> '
```

Replace with:
```python
    st.markdown(
        '<div style="background:rgba(6,182,212,0.06);border:1px solid rgba(6,182,212,0.2);border-radius:8px;'
        'padding:0.8rem 1.1rem;font-size:0.86rem;color:#67e8f9;">'
        '💡 <strong style="color:#f1f5f9;">PySpark &amp; Spark Classic → Serverless</strong> '
```

- [ ] **Step 6: Commit**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
git add lb_migration_platform_ui/app.py
git commit -m "feat: dark glass theme — Get Started inline HTML dark colours"
```

---

### Task 4: Fix inline HTML — Analyzer + Transpiler intro banners

**Files:**
- Modify: `lb_migration_platform_ui/app.py` (lines ~1629-1640, ~1667-1680, and the info-banner in Transpiler)

- [ ] **Step 1: Analyzer intro text**

Find (around line 1631):
```python
    st.markdown("""
    <div style="color:#475569;font-size:0.92rem;max-width:680px;margin-bottom:1.5rem;">
```
Replace `color:#475569` → `color:#94a3b8`:
```python
    st.markdown("""
    <div style="color:#94a3b8;font-size:0.92rem;max-width:680px;margin-bottom:1.5rem;">
```

- [ ] **Step 2: Analyzer tech info card (background + text)**

Find (around line 1668):
```python
        st.markdown(f"""
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:1rem 1.25rem;margin-top:0.75rem;">
            <div style="font-weight:700;color:#111827;font-size:1rem;margin-bottom:0.2rem;">
```
Replace:
- `background:#f9fafb` → `background:rgba(255,255,255,0.03)`
- `border:1px solid #e5e7eb` → `border:1px solid rgba(255,255,255,0.08)`
- `color:#111827` → `color:#f1f5f9`

Search for any remaining occurrences of `color:#111827`, `color:#0f172a`, `background:#f9fafb`, `background:#f8fafc`, `background:#fff`, `border:1px solid #e2e8f0`, `border:1px solid #e5e7eb` within inline HTML strings in the file and apply the mapping:

| Old | New |
|-----|-----|
| `color:#0f172a` | `color:#f1f5f9` |
| `color:#111827` | `color:#f1f5f9` |
| `color:#475569` | `color:#94a3b8` |
| `color:#64748b` | `color:#94a3b8` |
| `background:#fff` (in inline style) | `background:rgba(255,255,255,0.03)` |
| `background:#f8fafc` | `background:rgba(255,255,255,0.03)` |
| `background:#f9fafb` | `background:rgba(255,255,255,0.03)` |
| `background:#f1f5f9` | `background:rgba(255,255,255,0.05)` |
| `border:1px solid #e2e8f0` | `border:1px solid rgba(255,255,255,0.08)` |
| `border:1px solid #e5e7eb` | `border:1px solid rgba(255,255,255,0.08)` |
| `border-left:1px solid #e2e8f0` | `border-left:1px solid rgba(255,255,255,0.08)` |
| `border-bottom:1px solid #e2e8f0` | `border-bottom:1px solid rgba(255,255,255,0.08)` |
| `border-top:1px solid #e2e8f0` | `border-top:1px solid rgba(255,255,255,0.08)` |

Use the Replace All feature in the editor or grep to find and fix all occurrences in inline HTML strings. Only change values inside `st.markdown(...)` calls — do not change Python logic, variable names, or CSS in the main CSS block from Task 1.

- [ ] **Step 3: Commit**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
git add lb_migration_platform_ui/app.py
git commit -m "feat: dark glass theme — Analyzer/Transpiler inline HTML dark colours"
```

---

### Task 5: Verify and smoke-test

**Files:** none (run the app)

- [ ] **Step 1: Run the app locally**

```bash
source "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/lb/bin/activate"
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform/lb_migration_platform_ui"
streamlit run app.py
```

- [ ] **Step 2: Visual checklist**

Open `http://localhost:8501` in browser and verify:
- [ ] Background is dark `#09090e` with visible orange/indigo/cyan gradient orbs
- [ ] Top nav bar appears (52px, frosted glass): Syren logo pill + nav links + "⚡ 13 Dialects" badge
- [ ] No sidebar visible
- [ ] Active page link is orange (`#FF3621`)
- [ ] Clicking nav links navigates to the correct page (URL changes to `?page=Analyzer` etc.)
- [ ] All card backgrounds are dark glass (not white)
- [ ] Input text is visible (white `#f1f5f9`, not black on black)
- [ ] Buttons are orange primary style
- [ ] Get Started page: table has dark rows, tech lists are readable

- [ ] **Step 3: Run existing tests to confirm no regressions**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
PYTHONPATH=. pytest tests/test_ssrs_converter.py tests/test_oozie_converter.py -v
```
Expected: all tests pass (theme changes don't affect modules).

- [ ] **Step 4: Final commit**

```bash
cd "/Users/tanishkchaturvedi/Desktop/Tanishk Chaturvedi/WORK/CONSULATNCY/SYREN/lakebrdige/Lb-Migration-Platform"
git add lb_migration_platform_ui/app.py
git commit -m "feat: glass premium dark theme — complete visual overhaul"
```
