import re

from bs4 import BeautifulSoup

_WARRANTY_RE = re.compile("warranty", re.I)


def extract_warranty(soup: BeautifulSoup) -> str | None:
    """
    Best-effort warranty text from a product detail page. Tries known
    spec-table shapes before giving up; returns None when nothing matches
    (caller falls back to "Wala").
    """
    # Shape 1: explicit label/value spec rows, e.g.
    # <span class="spec-label">Warranty</span><span class="spec-value">...</span>
    for label in soup.find_all(string=_WARRANTY_RE):
        label_el = label.parent
        if label_el is None or label_el.get_text(strip=True).lower() != "warranty":
            continue
        value_el = label_el.find_next_sibling()
        if value_el is not None:
            text = value_el.get_text(" ", strip=True)
            if text:
                return text

    # Shape 2: a "Warranty Term" heading followed by a <ul> of terms, e.g.
    # <div><strong>Warranty Term</strong></div><ul><li>Compressor: 10 YEARS</li>...
    for heading in soup.find_all(string=re.compile(r"warranty\s*term", re.I)):
        container = heading.parent
        if container is None:
            continue
        block = container if container.name != "strong" else container.parent
        ul = block.find_next_sibling("ul") if block else None
        if ul is not None:
            items = [re.sub(r"\s+", " ", li.get_text()).strip() for li in ul.find_all("li")]
            items = [i for i in items if i]
            if items:
                return "; ".join(items)

    return None
