"""Greeting by country of citizenship, in the language's own script.
Gender-neutral wherever the language allows (e.g. "Hola" rather than "Bienvenido").
Works offline with the fonts already on your computer. Change it under Settings."""

RTL = {"ar", "fa", "ur", "he"}

# country: (Latin spelling, native script, language code)
GREETINGS = {
    "AFGHANISTAN": ("Khosh amadid", "خوش آمدید", "fa"),
    "ARGENTINA": ("Hola", "Hola", "es"), "BOLIVIA": ("Hola", "Hola", "es"), "CHILE": ("Hola", "Hola", "es"),
    "COLOMBIA": ("Hola", "Hola", "es"), "COSTA RICA": ("Hola", "Hola", "es"), "CUBA": ("Hola", "Hola", "es"),
    "DOMINICAN REPUBLIC": ("Hola", "Hola", "es"), "ECUADOR": ("Hola", "Hola", "es"),
    "EL SALVADOR": ("Hola", "Hola", "es"), "GUATEMALA": ("Hola", "Hola", "es"), "HONDURAS": ("Hola", "Hola", "es"),
    "MEXICO": ("Hola", "Hola", "es"), "PANAMA": ("Hola", "Hola", "es"), "PERU": ("Hola", "Hola", "es"),
    "SPAIN": ("Hola", "Hola", "es"), "VENEZUELA": ("Hola", "Hola", "es"),
    "AUSTRALIA": ("Welcome", "Welcome", "en"), "CANADA": ("Welcome", "Welcome", "en"),
    "NIGERIA": ("Welcome", "Welcome", "en"), "UNITED KINGDOM": ("Welcome", "Welcome", "en"),
    "ZIMBABWE": ("Welcome", "Welcome", "en"),
    "BANGLADESH": ("Shagotom", "স্বাগতম", "bn"),
    "BRAZIL": ("Olá", "Olá", "pt"), "PORTUGAL": ("Olá", "Olá", "pt"),
    "CAMEROON": ("Bienvenue", "Bienvenue", "fr"), "FRANCE": ("Bienvenue", "Bienvenue", "fr"),
    "CHINA": ("Huānyíng", "欢迎", "zh-Hans"), "TAIWAN": ("Huānyíng", "歡迎", "zh-Hant"),
    "HONG KONG": ("Fun ying", "歡迎", "zh-Hant"),
    "EGYPT": ("Ahlan wa sahlan", "أهلاً وسهلاً", "ar"), "IRAQ": ("Ahlan wa sahlan", "أهلاً وسهلاً", "ar"),
    "JORDAN": ("Ahlan wa sahlan", "أهلاً وسهلاً", "ar"), "KUWAIT": ("Ahlan wa sahlan", "أهلاً وسهلاً", "ar"),
    "LEBANON": ("Ahlan wa sahlan", "أهلاً وسهلاً", "ar"), "QATAR": ("Ahlan wa sahlan", "أهلاً وسهلاً", "ar"),
    "SAUDI ARABIA": ("Ahlan wa sahlan", "أهلاً وسهلاً", "ar"), "SYRIA": ("Ahlan wa sahlan", "أهلاً وسهلاً", "ar"),
    "UNITED ARAB EMIRATES": ("Ahlan wa sahlan", "أهلاً وسهلاً", "ar"), "MOROCCO": ("Marhaba", "مرحبا", "ar"),
    "ETHIOPIA": ("Selam", "ሰላም", "am"),
    "GERMANY": ("Willkommen", "Willkommen", "de"),
    "GHANA": ("Akwaaba", "Akwaaba", "ak"),
    "GREECE": ("Yia sou", "Γεια σου", "el"),
    "INDIA": ("Namaste", "नमस्ते", "hi"),
    "INDONESIA": ("Selamat datang", "Selamat datang", "id"), "MALAYSIA": ("Selamat datang", "Selamat datang", "ms"),
    "IRAN": ("Khosh amadid", "خوش آمدید", "fa"),
    "ISRAEL": ("Shalom", "שלום", "he"),
    "ITALY": ("Ciao", "Ciao", "it"),
    "JAPAN": ("Yōkoso", "ようこそ", "ja"),
    "KAZAKHSTAN": ("Qosh keldiniz", "Қош келдіңіз", "kk"),
    "KENYA": ("Karibu", "Karibu", "sw"), "TANZANIA": ("Karibu", "Karibu", "sw"), "UGANDA": ("Karibu", "Karibu", "sw"),
    "KOREA": ("Annyeonghaseyo", "안녕하세요", "ko"),
    "MYANMAR": ("Mingalaba", "မင်္ဂလာပါ", "my"),
    "NEPAL": ("Swagatam", "स्वागतम्", "ne"),
    "NETHERLANDS": ("Welkom", "Welkom", "nl"),
    "NORWAY": ("Velkommen", "Velkommen", "nb"),
    "PAKISTAN": ("Khush aamdeed", "خوش آمدید", "ur"),
    "PHILIPPINES": ("Mabuhay", "Mabuhay", "tl"),
    "POLAND": ("Witaj", "Witaj", "pl"),
    "RUSSIA": ("Dobro pozhalovat", "Добро пожаловать", "ru"),
    "SRI LANKA": ("Ayubowan", "ආයුබෝවන්", "si"),
    "SWEDEN": ("Välkommen", "Välkommen", "sv"),
    "THAILAND": ("Sawasdee", "สวัสดี", "th"),
    "TURKEY": ("Hoş geldiniz", "Hoş geldiniz", "tr"), "TÜRKIYE": ("Hoş geldiniz", "Hoş geldiniz", "tr"),
    "UKRAINE": ("Laskavo prosymo", "Ласкаво просимо", "uk"),
    "UZBEKISTAN": ("Xush kelibsiz", "Xush kelibsiz", "uz"),
    "VIETNAM": ("Xin chào", "Xin chào", "vi"),
}


def _lookup(country: str):
    c = (country or "").upper().strip()
    if not c:
        return None
    if c in GREETINGS:
        return GREETINGS[c]
    for name, entry in GREETINGS.items():  # e.g. "KOREA, REPUBLIC OF", "VIET NAM" variants
        if name in c or c in name:
            return entry
    return None


def for_country(country: str, native: bool = True) -> dict | None:
    entry = _lookup(country)
    if not entry:
        return None
    latin, script, lang = entry
    if native:
        return {"text": script, "lang": lang, "dir": "rtl" if lang in RTL else "ltr", "latin": latin}
    return {"text": latin, "lang": "en", "dir": "ltr", "latin": latin}


def resolve(profile: dict) -> dict:
    mode = profile.get("greeting_mode", "auto")
    if mode == "custom" and profile.get("greeting"):
        return {"text": profile["greeting"], "lang": "", "dir": "auto", "latin": profile["greeting"]}
    if mode == "off":
        return {"text": "Hello", "lang": "en", "dir": "ltr", "latin": "Hello"}
    return (for_country(profile.get("country", ""), native=profile.get("native_script", True))
            or {"text": "Welcome", "lang": "en", "dir": "ltr", "latin": "Welcome"})
