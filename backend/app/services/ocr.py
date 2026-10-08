"""Seed packet OCR (F11): photo -> crop, variety, lot number, dates.

Tesseract (Apache 2.0) with English, Telugu and Hindi language packs. Labels
on Indian seed packets follow the Seeds Act format (Kind, Variety, Lot No,
Date of test, Valid upto, Germination, Net weight), which the regexes target.
"""
import io
import re

LABELS = {
    "crop": r"(?:kind|crop|పంట|फसल)\s*[:\-]?\s*([^\n]+)",
    "variety": r"(?:variety|var\.|రకం|किस्म)\s*[:\-]?\s*([^\n]+)",
    "lot_no": r"lot\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Z0-9/\-]+)",
    "date_of_test": r"date\s*of\s*test(?:ing)?\s*[:\-]?\s*([0-9]{1,2}[./\-][0-9]{1,2}[./\-][0-9]{2,4}|[A-Za-z]{3,9}\s*[0-9]{4})",
    "valid_upto": r"(?:valid\s*up\s*to|valid\s*till|expiry|exp\.?)\s*[:\-]?\s*([0-9]{1,2}[./\-][0-9]{1,2}[./\-][0-9]{2,4}|[A-Za-z]{3,9}\s*[0-9]{4})",
    "germination_pct": r"germination\s*(?:\(%\)|%)?\s*[:\-]?\s*(\d{2,3})",
    "net_weight": r"net\s*(?:wt\.?|weight|content)\s*[:\-]?\s*([\d.]+\s*(?:kg|g|gm|grams?))",
}


def read_image(data: bytes) -> str:
    import pytesseract
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
    if max(img.size) < 1500:
        scale = 1500 / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return pytesseract.image_to_string(img, lang="eng+tel+hin")


def parse_seed_packet(text: str) -> dict:
    out = {}
    for key, pattern in LABELS.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            out[key] = m.group(1).strip(" .:-")
    if "germination_pct" in out:
        out["germination_pct"] = int(out["germination_pct"])
    return out


# --------------------------------------------------------------- Soil Health Card

NUM = r"[:\-\s]*([0-9]+(?:\.[0-9]+)?)"
SOIL_LABELS = {
    "n_kg_ha": r"(?:available\s*)?nitrogen\s*(?:\(N\))?(?:\s*kg/ha)?" + NUM,
    "p_kg_ha": r"(?:available\s*)?phosph\w*\s*(?:\(P\))?(?:\s*kg/ha)?" + NUM,
    "k_kg_ha": r"(?:available\s*)?potass\w*\s*(?:\(K\))?(?:\s*kg/ha)?" + NUM,
    "ph": r"\bpH\b" + NUM,
    "oc_pct": r"organic\s*carbon\s*(?:\(OC\))?(?:\s*%)?" + NUM,
    "ec_ds_m": r"\bEC\b(?:\s*\(?dS/m\)?)?" + NUM,
    "zn_ppm": r"(?:zinc|\bZn\b)\s*(?:\(Zn\))?(?:\s*ppm)?" + NUM,
}


def parse_soil_card(text: str) -> dict:
    """Values from a Soil Health Card photo (as printed: available N, P, K in kg/ha)."""
    out = {}
    for key, pattern in SOIL_LABELS.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            out[key] = float(m.group(1))
    return out
