import re
from typing import Any


def clean_text(value: Any):
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def to_float(value: Any):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def first_attr(attributes: list[dict], ids_or_names: list[str]):
    wanted = {x.casefold() for x in ids_or_names}
    for attr in attributes or []:
        attr_id = str(attr.get("id") or "").casefold()
        name = str(attr.get("name") or "").casefold()
        if attr_id in wanted or name in wanted:
            return clean_text(attr.get("value_name"))
    return None
