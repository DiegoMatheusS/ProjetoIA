"""Explicit label/value adapters for official specification layouts."""
from urllib.parse import urlparse

LAYOUTS = {
    "asus.com": [(".TechSpec__row", ".TechSpec__title", ".TechSpec__info"), (".spec-item", ".spec-title", ".spec-content")],
    "msi.com": [(".specification-item", ".specification-title", ".specification-content")],
    "gigabyte.com": [(".spec-row", ".spec-title", ".spec-desc")],
    "corsair.com": [(".tech-spec-row", ".tech-spec-label", ".tech-spec-value")],
    "kingston.com": [(".spec-row", ".spec-label", ".spec-value")],
}


def manufacturer_attributes(soup, url):
    host = (urlparse(url).hostname or '').lower()
    attrs = []
    for domain, layouts in LAYOUTS.items():
        if host != domain and not host.endswith('.' + domain):
            continue
        for row_sel, label_sel, value_sel in layouts:
            for row in soup.select(row_sel)[:250]:
                label, value = row.select_one(label_sel), row.select_one(value_sel)
                if label and value:
                    name, text = label.get_text(' ', strip=True), value.get_text(' ', strip=True)
                    if name and text and len(name) <= 160 and len(text) <= 1000:
                        attrs.append({'name': name, 'value_name': text, 'id': None})
    return attrs
