"""Turn a spoken or typed diary note into a structured record (F11).

Rule-based, so it works offline and in Telugu, Hindi and English. It looks
for the activity (keywords in all three languages), product, quantity, unit
and money. Anything it is not sure about stays empty rather than guessed.
"""
import re

ACTIVITY_WORDS = {
    "sowing": ["sow", "sowed", "sown", "planted", "transplant", "nursery", "విత్త", "నాట", "నారు", "बुवाई", "बोया", "रोपाई"],
    "fertilizer": ["fertili", "urea", "dap", "potash", "complex", "zinc", "యూరియా", "ఎరువు", "డీఏపీ", "पोटाश",
                   "यूरिया", "खाद", "डीएपी"],
    "irrigation": ["irrigat", "water", "నీరు", "నీళ్లు", "తడి", "पानी", "सिंचाई"],
    "pesticide": ["spray", "pesticide", "insecticide", "fungicide", "పురుగు", "మందు", "పిచికారీ", "छिड़काव",
                  "कीटनाशक", "दवा"],
    "weeding": ["weed", "కలుపు", "निराई", "खरपतवार"],
    "harvest": ["harvest", "cut the crop", "కోత", "కోశా", "कटाई", "काटा"],
    "sale": ["sold", "sell", "market", "అమ్మ", "बेचा", "मंडी"],
}
PRODUCTS = {
    "urea": ["urea", "యూరియా", "यूरिया"], "dap": ["dap", "డీఏపీ", "डीएपी"], "potash": ["potash", "పొటాష్", "पोटाश"],
    "zinc": ["zinc", "జింక్", "जिंक"],
}
UNITS = {
    "bag": ["bags", "bag", "బస్తాలు", "బస్తా", "బస్తాల", "बोरी", "बोरे", "कट्टे"],
    "kg": ["kg", "kgs", "kilo", "కిలోలు", "కిలో", "किलो"],
    "quintal": ["quintal", "qtl", "క్వింటాళ్లు", "క్వింటాల్", "क्विंटल"],
    "litre": ["litre", "liter", "ltr", "లీటర్లు", "లీటర్", "लीटर"],
    "acre": ["acres", "acre", "ఎకరాలు", "ఎకరం", "एकड़"],
    "hour": ["hours", "hour", "hrs", "గంటలు", "घंटे"],
}
MONEY = re.compile(r"(?:rs\.?|₹|inr)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:rs|rupees|రూపాయలు|రూ|रुपये|रुपए)",
                   re.IGNORECASE)
NUMBER = r"(\d+(?:\.\d+)?)"
BAG_KG = {"urea": 45, "dap": 50, "potash": 50}


def _find(words: dict[str, list[str]], text: str) -> str | None:
    best, pos = None, None
    for key, keys in words.items():
        for k in keys:
            i = text.find(k)
            if i >= 0 and (pos is None or i < pos):
                best, pos = key, i
    return best


def parse_note(text: str) -> dict:
    low = text.lower()
    activity = _find(ACTIVITY_WORDS, low) or "observation"
    product = _find(PRODUCTS, low)
    if product and activity == "observation":
        activity = "fertilizer"

    money = None
    m = MONEY.search(low)
    if m:
        money = float((m.group(1) or m.group(2)).replace(",", ""))
    stripped = MONEY.sub(" ", low)

    quantity = unit = None
    for u, keys in UNITS.items():
        for k in keys:
            mm = re.search(NUMBER + r"\s*" + re.escape(k), stripped)
            if mm:
                quantity, unit = float(mm.group(1)), u
                break
        if unit:
            break

    record = {"activity_type": activity, "product": product, "quantity": quantity, "unit": unit, "cost_rs": money}
    if unit == "bag" and product in BAG_KG and quantity:
        record["quantity_kg"] = quantity * BAG_KG[product]
    return {k: v for k, v in record.items() if v is not None}
