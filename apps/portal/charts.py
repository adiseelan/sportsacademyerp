"""
Dependency-free, CSP-safe SVG charts (no client JS, no CDN). Each function
returns a SafeString ready to drop into a template.
"""
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe


def _nice_max(value):
    if value <= 0:
        return 1
    return value


def bar_chart(pairs, width=360, height=190, unit="₹"):
    """pairs: list of (label, number). Rendered as inline SVG (deterministic,
    responsive, CSP-safe) — no flexbox percentage-height quirks."""
    pairs = list(pairs)
    if not pairs:
        return mark_safe('<p class="muted">No data yet.</p>')
    top = float(_nice_max(max(v for _, v in pairs)))
    pad_top, pad_bottom = 20, 34
    plot_h = height - pad_top - pad_bottom
    n = len(pairs)
    slot = width / n
    bw = min(46.0, slot * 0.55)
    parts = []
    for i, (label, value) in enumerate(pairs):
        h = max(3.0, (float(value) / top) * plot_h) if top else 3.0
        x = i * slot + (slot - bw) / 2
        y = pad_top + plot_h - h
        cx = x + bw / 2
        parts.append(
            format_html(
                '<rect x="{}" y="{}" width="{}" height="{}" rx="5" class="bar-rect"></rect>'
                '<text x="{}" y="{}" class="bar-val">{}{}</text>'
                '<text x="{}" y="{}" class="bar-lbl">{}</text>',
                f"{x:.1f}", f"{y:.1f}", f"{bw:.1f}", f"{h:.1f}",
                f"{cx:.1f}", f"{y - 5:.1f}", unit, _fmt(value),
                f"{cx:.1f}", f"{height - 8}", _truncate(label),
            )
        )
    return format_html(
        '<svg viewBox="0 0 {} {}" class="bar-chart" role="img" '
        'preserveAspectRatio="xMidYMid meet">{}</svg>',
        width, height, mark_safe("".join(parts)),
    )


def _truncate(label, n=10):
    s = str(label)
    return s if len(s) <= n else s[: n - 1] + "…"


def line_chart(points, width=520, height=180, unit="₹"):
    """points: list of (label, number). Simple sparkline-style area line."""
    points = list(points)
    if not points:
        return mark_safe('<p class="muted">No data yet.</p>')
    top = _nice_max(max(v for _, v in points))
    n = len(points)
    pad = 8
    inner_w = width - pad * 2
    inner_h = height - pad * 2 - 18
    step = inner_w / max(1, n - 1)

    coords = []
    for i, (_, v) in enumerate(points):
        x = pad + i * step
        y = pad + inner_h - (v / top) * inner_h
        coords.append((x, y))

    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"{pad},{pad + inner_h} " + poly + f" {pad + inner_w:.1f},{pad + inner_h}"
    dots = format_html_join(
        "", '<circle cx="{}" cy="{}" r="3" class="ln-dot"></circle>',
        ((f"{x:.1f}", f"{y:.1f}") for x, y in coords),
    )
    labels = format_html_join(
        "",
        '<text x="{}" y="{}" class="ln-lbl">{}</text>',
        ((f"{pad + i * step:.1f}", height - 4, lbl) for i, (lbl, _) in enumerate(points)),
    )
    return format_html(
        '<svg viewBox="0 0 {} {}" class="line-chart" preserveAspectRatio="none" '
        'role="img">'
        '<polygon points="{}" class="ln-area"></polygon>'
        '<polyline points="{}" class="ln-line" fill="none"></polyline>'
        '{}{}</svg>',
        width, height, area, poly, dots, labels,
    )


def donut(paid, outstanding, size=140):
    total = paid + outstanding
    if total <= 0:
        return mark_safe('<p class="muted">No data yet.</p>')
    frac = paid / total
    r = size / 2 - 12
    import math

    c = 2 * math.pi * r
    dash = c * frac
    cx = cy = size / 2
    # Pre-format all floats to plain strings — format_html escapes args to
    # SafeString, which cannot take a ':.1f' format spec inside the template.
    return format_html(
        '<svg viewBox="0 0 {s} {s}" class="donut" role="img" aria-label="Collected vs outstanding">'
        '<circle cx="{cx}" cy="{cy}" r="{r}" class="donut-track"></circle>'
        '<circle cx="{cx}" cy="{cy}" r="{r}" class="donut-val" '
        'stroke-dasharray="{dash} {c}" transform="rotate(-90 {cx} {cy})"></circle>'
        '<text x="{cx}" y="{cy}" class="donut-pct">{pct}%</text></svg>',
        s=size, cx=f"{cx:.1f}", cy=f"{cy:.1f}", r=f"{r:.1f}",
        dash=f"{dash:.1f}", c=f"{c:.1f}", pct=round(frac * 100),
    )


def _fmt(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return v
    if v >= 10_000_000:
        return f"{v/10_000_000:.1f}Cr"
    if v >= 100_000:
        return f"{v/100_000:.1f}L"
    if v >= 1000:
        return f"{v/1000:.1f}k"
    return f"{v:.0f}"
