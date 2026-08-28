"""Shared navigation for Callahan dashboard pages."""

from __future__ import annotations

import html


NAV_ITEMS = [
    ("Board", "/v2", True),
    ("DVI Queue", "/dvi", True),
    ("Activity", "/activity", True),
    ("Timeline", "/timeline", True),
    ("Drew", "/drew", True),
    ("Mitch", "/mitch", True),
    ("Sanity Check", "/sanity-check", True),
]


def render_nav(active_page: str = "") -> str:
    active = str(active_page or "").strip().lower()
    links = []
    for label, href, exists in NAV_ITEMS:
        key = label.lower()
        classes = ["callahan-nav-link"]
        if key == active:
            classes.append("active")
        if not exists:
            classes.append("dim")
        badge = ' <span class="callahan-nav-badge">NEW</span>' if label == "Timeline" else ""
        links.append(
            f'<a class="{" ".join(classes)}" href="{html.escape(href)}">'
            f"{html.escape(label)}{badge}</a>"
        )
    return f"""
<nav class="callahan-nav" aria-label="Callahan dashboard navigation">
  <style>
    .callahan-nav {{
      background:#0f172a;color:#fff;border-bottom:1px solid rgba(148,163,184,.24);
      padding:10px 14px;display:flex;gap:8px;align-items:center;overflow-x:auto;
      white-space:nowrap;font-family:Inter,ui-sans-serif,system-ui,Arial,sans-serif;
      -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
    }}
    .callahan-nav::-webkit-scrollbar {{height:8px}}
    .callahan-nav::-webkit-scrollbar-thumb {{background:#334155;border-radius:999px}}
    .callahan-nav-link {{
      color:#fff;text-decoration:none;font-size:12px;font-weight:850;letter-spacing:.02em;
      padding:8px 10px;border-radius:9px;border:1px solid transparent;display:inline-flex;
      align-items:center;gap:6px;opacity:.96;
    }}
    .callahan-nav-link:hover {{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.18)}}
    .callahan-nav-link.active {{
      background:rgba(20,184,166,.14);border-color:rgba(45,212,191,.55);
      box-shadow:inset 0 -2px 0 #2dd4bf;color:#ecfeff;
    }}
    .callahan-nav-link.dim {{opacity:.46}}
    .callahan-nav-badge {{
      border:1px solid rgba(45,212,191,.65);color:#99f6e4;border-radius:999px;
      padding:1px 5px;font-size:9px;font-weight:950;letter-spacing:.08em;
    }}
    @media print {{
      .callahan-nav {{ display:none !important; }}
    }}
  </style>
  {"".join(links)}
</nav>
"""
