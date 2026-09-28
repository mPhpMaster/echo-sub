# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
import os

# Whisper language code -> (Arabic name, NLLB-200 code); Arabic names are kept as search aliases
LANGUAGES = {
    "ar": ("العربية", "arb_Arab"),
    "ary": ("العربية المغربية (الدارجة)", "ary_Arab"),  # Moroccan Arabic; Whisper hears it as "ar"
    "en": ("الإنجليزية", "eng_Latn"),
    "fr": ("الفرنسية", "fra_Latn"),
    "de": ("الألمانية", "deu_Latn"),
    "es": ("الإسبانية", "spa_Latn"),
    "it": ("الإيطالية", "ita_Latn"),
    "pt": ("البرتغالية", "por_Latn"),
    "ru": ("الروسية", "rus_Cyrl"),
    "tr": ("التركية", "tur_Latn"),
    "fa": ("الفارسية", "pes_Arab"),
    "ur": ("الأردية", "urd_Arab"),
    "hi": ("الهندية", "hin_Deva"),
    "bn": ("البنغالية", "ben_Beng"),
    "zh": ("الصينية", "zho_Hans"),
    "yue": ("الكانتونية", "yue_Hant"),
    "ja": ("اليابانية", "jpn_Jpan"),
    "ko": ("الكورية", "kor_Hang"),
    "id": ("الإندونيسية", "ind_Latn"),
    "ms": ("الماليزية", "zsm_Latn"),
    "th": ("التايلاندية", "tha_Thai"),
    "vi": ("الفيتنامية", "vie_Latn"),
    "tl": ("الفلبينية", "tgl_Latn"),
    "nl": ("الهولندية", "nld_Latn"),
    "pl": ("البولندية", "pol_Latn"),
    "uk": ("الأوكرانية", "ukr_Cyrl"),
    "sv": ("السويدية", "swe_Latn"),
    "no": ("النرويجية", "nob_Latn"),
    "nn": ("النرويجية (نينورسك)", "nno_Latn"),
    "da": ("الدنماركية", "dan_Latn"),
    "fi": ("الفنلندية", "fin_Latn"),
    "el": ("اليونانية", "ell_Grek"),
    "he": ("العبرية", "heb_Hebr"),
    "cs": ("التشيكية", "ces_Latn"),
    "sk": ("السلوفاكية", "slk_Latn"),
    "sl": ("السلوفينية", "slv_Latn"),
    "ro": ("الرومانية", "ron_Latn"),
    "hu": ("المجرية", "hun_Latn"),
    "bg": ("البلغارية", "bul_Cyrl"),
    "sr": ("الصربية", "srp_Cyrl"),
    "hr": ("الكرواتية", "hrv_Latn"),
    "bs": ("البوسنية", "bos_Latn"),
    "mk": ("المقدونية", "mkd_Cyrl"),
    "sq": ("الألبانية", "als_Latn"),
    "lt": ("الليتوانية", "lit_Latn"),
    "lv": ("اللاتفية", "lvs_Latn"),
    "et": ("الإستونية", "est_Latn"),
    "be": ("البيلاروسية", "bel_Cyrl"),
    "is": ("الآيسلندية", "isl_Latn"),
    "ca": ("الكتالونية", "cat_Latn"),
    "gl": ("الجاليكية", "glg_Latn"),
    "eu": ("الباسكية", "eus_Latn"),
    "cy": ("الويلزية", "cym_Latn"),
    "mt": ("المالطية", "mlt_Latn"),
    "lb": ("اللوكسمبورغية", "ltz_Latn"),
    "af": ("الأفريكانية", "afr_Latn"),
    "sw": ("السواحيلية", "swh_Latn"),
    "am": ("الأمهرية", "amh_Ethi"),
    "so": ("الصومالية", "som_Latn"),
    "ha": ("الهوسا", "hau_Latn"),
    "yo": ("اليوروبا", "yor_Latn"),
    "ln": ("اللينغالا", "lin_Latn"),
    "sn": ("الشونا", "sna_Latn"),
    "mg": ("الملغاشية", "plt_Latn"),
    "ta": ("التاميلية", "tam_Taml"),
    "te": ("التيلوغوية", "tel_Telu"),
    "ml": ("المالايالامية", "mal_Mlym"),
    "kn": ("الكانادية", "kan_Knda"),
    "mr": ("الماراثية", "mar_Deva"),
    "gu": ("الغوجاراتية", "guj_Gujr"),
    "pa": ("البنجابية", "pan_Guru"),
    "ne": ("النيبالية", "npi_Deva"),
    "si": ("السنهالية", "sin_Sinh"),
    "as": ("الأسامية", "asm_Beng"),
    "sd": ("السندية", "snd_Arab"),
    "ps": ("البشتو", "pbt_Arab"),
    "km": ("الخميرية", "khm_Khmr"),
    "lo": ("اللاوية", "lao_Laoo"),
    "my": ("البورمية", "mya_Mymr"),
    "ka": ("الجورجية", "kat_Geor"),
    "hy": ("الأرمنية", "hye_Armn"),
    "az": ("الأذربيجانية", "azj_Latn"),
    "kk": ("الكازاخية", "kaz_Cyrl"),
    "uz": ("الأوزبكية", "uzn_Latn"),
    "tg": ("الطاجيكية", "tgk_Cyrl"),
    "tk": ("التركمانية", "tuk_Latn"),
    "mn": ("المنغولية", "khk_Cyrl"),
    "tt": ("التتارية", "tat_Cyrl"),
    "ba": ("الباشكيرية", "bak_Cyrl"),
    "jw": ("الجاوية", "jav_Latn"),
    "su": ("السوندانية", "sun_Latn"),
    "mi": ("الماورية", "mri_Latn"),
    "ht": ("الكريولية الهايتية", "hat_Latn"),
    "yi": ("اليديشية", "ydd_Hebr"),
    "fo": ("الفاروية", "fao_Latn"),
    "oc": ("الأوكسيتانية", "oci_Latn"),
    "bo": ("التبتية", "bod_Tibt"),
    "sa": ("السنسكريتية", "san_Deva"),
}

# Whisper language code -> English name shown in the interface
ENGLISH_NAMES = {
    "ar": "Arabic", "ary": "Moroccan Arabic (Darija)", "en": "English", "fr": "French", "de": "German",
    "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "ru": "Russian", "tr": "Turkish", "fa": "Persian", "ur": "Urdu", "hi": "Hindi",
    "bn": "Bengali", "zh": "Chinese", "yue": "Cantonese", "ja": "Japanese", "ko": "Korean", "id": "Indonesian",
    "ms": "Malay", "th": "Thai", "vi": "Vietnamese", "tl": "Filipino", "nl": "Dutch", "pl": "Polish",
    "uk": "Ukrainian", "sv": "Swedish", "no": "Norwegian", "nn": "Norwegian Nynorsk", "da": "Danish", "fi": "Finnish",
    "el": "Greek", "he": "Hebrew", "cs": "Czech", "sk": "Slovak", "sl": "Slovenian", "ro": "Romanian",
    "hu": "Hungarian", "bg": "Bulgarian", "sr": "Serbian", "hr": "Croatian", "bs": "Bosnian", "mk": "Macedonian",
    "sq": "Albanian", "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian", "be": "Belarusian", "is": "Icelandic",
    "ca": "Catalan", "gl": "Galician", "eu": "Basque", "cy": "Welsh", "mt": "Maltese", "lb": "Luxembourgish",
    "af": "Afrikaans", "sw": "Swahili", "am": "Amharic", "so": "Somali", "ha": "Hausa", "yo": "Yoruba",
    "ln": "Lingala", "sn": "Shona", "mg": "Malagasy", "ta": "Tamil", "te": "Telugu", "ml": "Malayalam",
    "kn": "Kannada", "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi", "ne": "Nepali", "si": "Sinhala",
    "as": "Assamese", "sd": "Sindhi", "ps": "Pashto", "km": "Khmer", "lo": "Lao", "my": "Burmese",
    "ka": "Georgian", "hy": "Armenian", "az": "Azerbaijani", "kk": "Kazakh", "uz": "Uzbek", "tg": "Tajik",
    "tk": "Turkmen", "mn": "Mongolian", "tt": "Tatar", "ba": "Bashkir", "jw": "Javanese", "su": "Sundanese",
    "mi": "Maori", "ht": "Haitian Creole", "yi": "Yiddish", "fo": "Faroese", "oc": "Occitan", "bo": "Tibetan",
    "sa": "Sanskrit",
}

# Language -> country whose flag represents it (ISO 3166 alpha-2, lowercase). A language spoken in many
# countries uses its best-known one; languages with no clear country have no flag and show their code instead.
FLAG_COUNTRY = {
    "ar": "sa", "ary": "ma", "en": "gb", "fr": "fr", "de": "de", "es": "es", "it": "it", "pt": "pt", "ru": "ru",
    "tr": "tr", "fa": "ir", "ur": "pk", "hi": "in", "bn": "bd", "zh": "cn", "yue": "hk", "ja": "jp",
    "ko": "kr", "id": "id", "ms": "my", "th": "th", "vi": "vn", "tl": "ph", "nl": "nl", "pl": "pl",
    "uk": "ua", "sv": "se", "no": "no", "nn": "no", "da": "dk", "fi": "fi", "el": "gr", "he": "il",
    "cs": "cz", "sk": "sk", "sl": "si", "ro": "ro", "hu": "hu", "bg": "bg", "sr": "rs", "hr": "hr",
    "bs": "ba", "mk": "mk", "sq": "al", "lt": "lt", "lv": "lv", "et": "ee", "be": "by", "is": "is",
    "cy": "gb-wls", "mt": "mt", "lb": "lu", "af": "za",
    "sw": "tz", "am": "et", "so": "so", "ha": "ng", "yo": "ng", "ln": "cd", "sn": "zw", "mg": "mg",
    "ta": "in", "te": "in", "ml": "in", "kn": "in", "mr": "in", "gu": "in", "pa": "in", "ne": "np",
    "si": "lk", "as": "in", "sd": "pk", "ps": "af", "km": "kh", "lo": "la", "my": "mm", "ka": "ge",
    "hy": "am", "az": "az", "kk": "kz", "uz": "uz", "tg": "tj", "tk": "tm", "mn": "mn", "tt": "ru",
    "ba": "ru", "jw": "id", "su": "id", "mi": "nz", "ht": "ht", "fo": "fo", "oc": "fr", "sa": "in",
}
FLAGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")

# Whisper codes that differ from Google Translate codes
GOOGLE_CODES = {"ary": "ar", "zh": "zh-CN", "yue": "zh-TW", "he": "iw", "jw": "jw", "nn": "no", "ba": "ru"}

RTL = {"ar", "ary", "fa", "ur", "he", "ps", "sd", "yi"}

# Languages Whisper can't tell apart from another one: speech is recognized with the Whisper code,
# but translated from / labeled as the specific variant when the user selects it as the spoken language.
WHISPER_CODES = {"ary": "ar"}
CODE_LABELS = {"ary": "AR-MA"}


def name(code):
    return ENGLISH_NAMES.get(code, code)


def arabic_name(code):
    return LANGUAGES.get(code, (code, None))[0]


def nllb_code(code):
    entry = LANGUAGES.get(code)
    return entry[1] if entry else None


def google_code(code):
    return GOOGLE_CODES.get(code, code)


def code_label(code):
    return CODE_LABELS.get(code, code.upper())


def whisper_code(code):
    return WHISPER_CODES.get(code, code)


def flag_path(code):
    """Path of the language's flag image, or None if it has none."""
    country = FLAG_COUNTRY.get(code)
    if not country:
        return None
    path = os.path.join(FLAGS_DIR, country + ".png")
    return path if os.path.exists(path) else None


# ---- writing systems -------------------------------------------------------
# Whisper sometimes writes a language in the wrong alphabet (English words in Russian letters, for
# example) when its context sentence is in another script. Comparing the text with the script its
# language is normally written in catches that.
_SCRIPT_RANGES = (
    ("latin", ((0x41, 0x24F), (0x1E00, 0x1EFF))),
    ("greek", ((0x370, 0x3FF),)),
    ("cyrillic", ((0x400, 0x52F),)),
    ("armenian", ((0x530, 0x58F),)),
    ("hebrew", ((0x590, 0x5FF), (0xFB1D, 0xFB4F))),
    ("arabic", ((0x600, 0x6FF), (0x750, 0x77F), (0x8A0, 0x8FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    ("syriac", ((0x700, 0x74F),)),
    ("thaana", ((0x780, 0x7BF),)),
    ("devanagari", ((0x900, 0x97F),)),
    ("bengali", ((0x980, 0x9FF),)),
    ("gurmukhi", ((0xA00, 0xA7F),)),
    ("gujarati", ((0xA80, 0xAFF),)),
    ("oriya", ((0xB00, 0xB7F),)),
    ("tamil", ((0xB80, 0xBFF),)),
    ("telugu", ((0xC00, 0xC7F),)),
    ("kannada", ((0xC80, 0xCFF),)),
    ("malayalam", ((0xD00, 0xD7F),)),
    ("sinhala", ((0xD80, 0xDFF),)),
    ("thai", ((0xE00, 0xE7F),)),
    ("lao", ((0xE80, 0xEFF),)),
    ("tibetan", ((0xF00, 0xFFF),)),
    ("myanmar", ((0x1000, 0x109F),)),
    ("georgian", ((0x10A0, 0x10FF), (0x1C90, 0x1CBF))),
    ("ethiopic", ((0x1200, 0x139F),)),
    ("khmer", ((0x1780, 0x17FF),)),
    ("kana", ((0x3040, 0x30FF), (0x31F0, 0x31FF))),
    ("hangul", ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF))),
    ("han", ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))),
)

# Languages written in something other than the Latin alphabet (everything else defaults to Latin).
# Languages that use several scripts in practice are left out, so their text is never questioned.
LANGUAGE_SCRIPTS = {
    "am": {"ethiopic"}, "ar": {"arabic"}, "ary": {"arabic"}, "as": {"bengali"}, "be": {"cyrillic"},
    "bg": {"cyrillic"}, "bn": {"bengali"}, "bo": {"tibetan"}, "dv": {"thaana"}, "el": {"greek"},
    "fa": {"arabic"}, "gu": {"gujarati"}, "he": {"hebrew"}, "hi": {"devanagari"}, "hy": {"armenian"},
    "ja": {"kana", "han"}, "ka": {"georgian"}, "km": {"khmer"}, "kn": {"kannada"}, "ko": {"hangul"},
    "lo": {"lao"}, "mk": {"cyrillic"}, "ml": {"malayalam"}, "mn": {"cyrillic"}, "mr": {"devanagari"},
    "my": {"myanmar"}, "ne": {"devanagari"}, "pa": {"gurmukhi"}, "ps": {"arabic"}, "ru": {"cyrillic"},
    "sa": {"devanagari"}, "sd": {"arabic"}, "si": {"sinhala"}, "ta": {"tamil"}, "te": {"telugu"},
    "tg": {"cyrillic"}, "th": {"thai"}, "tt": {"cyrillic"}, "uk": {"cyrillic"}, "ur": {"arabic"},
    "yi": {"hebrew"}, "yue": {"han"}, "zh": {"han"},
    # Written in both Latin and Cyrillic (or Arabic) letters: never questioned
    "az": None, "bs": None, "kk": None, "ky": None, "sr": None, "tk": None, "uz": None,
}


def text_script(text):
    """The writing system most of `text` is in, or None when it has too few letters to tell."""
    counts = {}
    for ch in text:
        code = ord(ch)
        for name, ranges in _SCRIPT_RANGES:
            if any(lo <= code <= hi for lo, hi in ranges):
                counts[name] = counts.get(name, 0) + 1
                break
    if sum(counts.values()) < 4:
        return None
    return max(counts, key=counts.get)


def fits_script(text, lang):
    """False only when `text` is clearly written in another alphabet than `lang` normally uses."""
    script = text_script(text)
    if script is None:
        return True
    expected = LANGUAGE_SCRIPTS.get(lang, {"latin"} if lang in LANGUAGES else None)
    return expected is None or script in expected
