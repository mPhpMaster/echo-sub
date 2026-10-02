# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Mohammad Al-Safadi
"""The words EchoSub listens for in a spoken command, in the languages it captions.

This file is only a vocabulary: words here can never do anything by themselves, they only pick one
of the fixed actions in `voice_commands.py`. Adding a language means adding words here.

Words are matched after `voice_commands.normalize`, so they are written lower-case and without
Arabic diacritics. Languages that do not put spaces between words (Chinese, Japanese, Korean,
Thai) are matched as plain text; the others must match whole words.
"""

OPEN_WORDS = (
    "open", "start", "launch", "run",                       # English
    "افتح", "فتح", "شغل", "اطلق",                           # Arabic
    "ouvre", "ouvrir", "lance", "demarre", "démarre",       # French
    "abre", "abrir", "inicia", "arranca",                   # Spanish
    "offne", "öffne", "offnen", "starte", "start mal",      # German
    "apri", "apre", "avvia",                                # Italian
    "abra", "abrir o", "inicie",                            # Portuguese
    "ac", "aç", "acar", "baslat", "başlat",                 # Turkish
    "открой", "открыть", "запусти", "запустить",            # Russian
    "باز کن", "بازکن", "اجرا کن",                            # Persian
    "کھولو", "کھولیں",                                       # Urdu
    "खोलो", "खोल", "चालू करो",                                # Hindi
    "buka", "jalankan",                                     # Indonesian / Malay
    "打开", "打開", "開啟", "开启",                            # Chinese
    "開いて", "ひらいて", "起動",                              # Japanese
    "열어", "열어줘", "실행",                                  # Korean
)

CLOSE_WORDS = (
    "close", "quit", "exit", "shut", "stop",                # English
    "اغلق", "غلق", "اقفل", "سكر", "اخرج من",                 # Arabic
    "ferme", "fermer", "quitte", "quitter",                 # French
    "cierra", "cerrar", "sal de", "salir de",               # Spanish
    "schliesse", "schließe", "beende", "schliess",          # German
    "chiudi", "chiudere", "esci da",                        # Italian
    "fecha", "fechar", "feche", "sair do",                  # Portuguese
    "kapat", "kapa", "cik", "çık",                          # Turkish
    "закрой", "закрыть", "выйди из",                        # Russian
    "ببند", "بستن",                                          # Persian
    "بند کرو", "بند کریں",                                    # Urdu
    "बंद करो", "बंद कर",                                      # Hindi
    "tutup",                                                # Indonesian / Malay
    "关闭", "關閉", "退出",                                    # Chinese
    "閉じて", "とじて", "終了",                                # Japanese
    "닫아", "닫아줘", "종료",                                  # Korean
)

APP_WORDS = {
    "calculator": (
        "calculator", "calc", "الحاسبه", "الاله الحاسبه", "حاسبه", "calculatrice", "calculette",
        "calculadora", "rechner", "taschenrechner", "calcolatrice", "hesap makinesi", "hesap makinasi",
        "калькулятор", "ماشین حساب", "کیلکولیٹر", "कैलकुलेटर", "kalkulator",
        "计算器", "計算機", "計算器", "電卓", "でんたく", "계산기",
    ),
    "notepad": (
        "notepad", "note pad", "المفكره", "الملاحظات", "المذكره", "bloc notes", "bloc de notes",
        "bloc de notas", "blocco note", "notizblock", "bloco de notas", "not defteri", "блокнот",
        "دفترچه یادداشت", "نوت پد", "नोटपैड", "记事本", "記事本", "メモ帳", "메모장",
    ),
    "paint": (
        "paint", "ms paint", "الرسام", "الرسم", "peinture", "dessin", "pintura", "dibujo",
        "malprogramm", "zeichenprogramm", "disegno", "resim", "paint programi", "paint программа",
        "нарисуй в пейнте", "пейнт", "نقاشی", "पेंट", "画图", "小画家", "ペイント", "그림판",
    ),
    "files": (
        "file explorer", "explorer", "files", "my computer", "this pc", "folder",
        "مستكشف الملفات", "المجلدات", "الملفات", "explorateur de fichiers", "explorateur",
        "explorador de archivos", "explorador", "datei explorer", "dateien", "esplora file",
        "gerenciador de arquivos", "dosya gezgini", "dosyalar", "проводник", "файлы",
        "فایل منیجر", "फाइल एक्सप्लोरर", "文件管理器", "资源管理器", "エクスプローラー", "파일 탐색기",
    ),
    "settings": (
        "settings", "windows settings", "الاعدادات", "اعدادات ويندوز", "parametres", "paramètres",
        "configuracion", "configuración", "ajustes", "einstellungen", "impostazioni", "configuracoes",
        "configurações", "ayarlar", "настройки", "تنظیمات", "सेटिंग्स", "pengaturan",
        "设置", "設定", "설정",
    ),
    "task manager": (
        "task manager", "مدير المهام", "gestionnaire des taches", "gestionnaire des tâches",
        "administrador de tareas", "task manager windows", "taskmanager", "gestione attivita",
        "gerenciador de tarefas", "gorev yoneticisi", "görev yöneticisi", "диспетчер задач",
        "مدیر وظایف", "टास्क मैनेजर", "任务管理器", "タスクマネージャー", "작업 관리자",
    ),
    "snipping tool": (
        "snipping tool", "screenshot tool", "snip", "اداه القص", "أداة القص", "لقطه الشاشه",
        "outil capture", "capture d ecran", "recortes", "captura de pantalla", "snipping",
        "ausschneiden und skizzieren", "strumento di cattura", "ferramenta de captura",
        "ekran alintisi", "ekran alıntısı", "ножницы", "снимок экрана", "ابزار برش",
        "स्निपिंग टूल", "截图工具", "切り取り領域", "캡처 도구",
    ),
    "on-screen keyboard": (
        "on screen keyboard", "virtual keyboard", "لوحه المفاتيح على الشاشه", "لوحه مفاتيح افتراضيه",
        "clavier visuel", "teclado en pantalla", "bildschirmtastatur", "tastiera su schermo",
        "teclado virtual", "ekran klavyesi", "экранная клавиатура", "صفحه کلید مجازی",
        "स्क्रीन कीबोर्ड", "屏幕键盘", "スクリーンキーボード", "화상 키보드",
    ),
    "magnifier": (
        "magnifier", "المكبر", "مكبر الشاشه", "loupe", "lupa", "bildschirmlupe", "lente di ingrandimento",
        "buyutec", "büyüteç", "экранная лупа", "лупа", "ذره بین", "मैग्नीफायर",
        "放大镜", "拡大鏡", "돋보기",
    ),
    "character map": (
        "character map", "خريطه المحارف", "جدول الرموز", "table des caracteres", "mapa de caracteres",
        "zeichentabelle", "mappa caratteri", "karakter haritasi", "таблица символов",
        "नक्शा वर्ण", "字符映射表", "文字コード表", "문자표",
    ),
    "chrome": ("chrome", "google chrome", "كروم", "جوجل كروم", "谷歌浏览器", "クローム", "크롬", "хром"),
    "edge": ("edge", "microsoft edge", "ايدج", "إيدج", "эдж", "边缘浏览器", "엣지"),
    "firefox": ("firefox", "fire fox", "فايرفوكس", "файрфокс", "火狐", "파이어폭스"),
    "vlc": ("vlc", "vlc player", "في ال سي", "مشغل vlc", "проигрыватель vlc", "브이엘씨"),
    "vs code": (
        "vs code", "visual studio code", "vscode", "code editor", "في اس كود", "محرر الكود",
        "редактор кода", "вс код", "代码编辑器", "비주얼 스튜디오 코드",
    ),
    "discord": ("discord", "ديسكورد", "دسكورد", "дискорд", "ディスコード", "디스코드", "迪斯科"),
    "steam": ("steam", "ستيم", "ستيم لانشر", "стим", "スチーム", "스팀"),
    "spotify": ("spotify", "سبوتيفاي", "спотифай", "スポティファイ", "스포티파이"),
}

LINK_WORDS = {
    "youtube": (
        "youtube", "you tube", "يوتيوب", "اليوتيوب", "youtub",
        "ютуб", "यूट्यूब", "油管", "ユーチューブ", "유튜브",
    ),
    "google": (
        "google", "جوجل", "قوقل", "غوغل", "гугл", "гугле", "गूगल", "谷歌", "グーグル", "구글",
    ),
}

# "go to ..." — the words that introduce a place to open. What follows is looked up in the folder
# list or read as a web address; see `voice_destinations.py` for what may then be opened.
GO_WORDS = (
    "go to", "goto", "go", "navigate to", "take me to", "browse to", "visit",   # English
    "اذهب الى", "اذهب", "روح", "روح الى", "انتقل الى", "انتقل", "وديني",           # Arabic
    "va a", "vas a", "aller a", "aller à",                                       # French / Spanish
    "geh zu", "gehe zu", "vai a", "ir para", "ve a",                             # German / Italian / Portuguese
    "git", "gidin",                                                              # Turkish
    "перейди", "перейти", "иди в", "открой сайт",                                # Russian
    "برو به", "برو",                                                             # Persian
    "جاؤ", "چلو",                                                                # Urdu
    "जाओ", "पर जाओ",                                                             # Hindi
    "去", "前往", "打开网址",                                                      # Chinese
    "に行く", "へ移動",                                                            # Japanese
    "로 이동", "이동",                                                             # Korean
    "ไปที่",                                                                      # Thai
)

# Calling off a command while its countdown is running. No wake word is needed and it works from
# any sound, because stopping something from happening can never itself do harm.
CANCEL_WORDS = (
    "no", "nope", "cancel", "stop", "dont", "don t", "wait", "nevermind", "never mind", "abort",
    "لا", "لأ", "الغ", "ألغ", "الغي", "بطل", "وقف", "اوقف", "استنى", "خلاص",
    "non", "annule", "nein", "halt", "no gracias", "cancela", "nao", "não", "hayır", "iptal",
    "нет", "отмена", "отмени", "نه", "لغو", "نہیں", "नहीं", "रहने दो",
    "不", "不要", "取消", "いいえ", "キャンセル", "아니", "취소", "ไม่",
)

# Muting your own microphone, said into that microphone. Both a name for it and a word for the
# action are needed, so merely mentioning a microphone does not switch it.
MIC_WORDS = (
    "microphone", "mic", "mike", "my mic", "my microphone",
    "المايك", "مايك", "الميكروفون", "مايكي", "صوتي",
    "micro", "microfono", "mikrofon", "микрофон", "माइक", "麦克风", "マイク", "마이크",
)
MIC_ACTION_WORDS = (
    "mute", "unmute", "off", "on", "stop", "start", "pause", "resume", "toggle", "silence", "cut",
    "اكتم", "كتم", "اسكت", "وقف", "اوقف", "طفي", "اطفي", "شغل", "افتح", "اقفل",
    "coupe", "silencia", "stumm", "sessize", "выключи", "включи", "банд каро",
    "بند کرو", "बंद", "静音", "ミュート", "음소거",
)

# "Type <words>" writes those words into whatever window has the keyboard. Everything after the
# word here is taken as the text, exactly as it was heard, so nothing else is read out of it.
TYPE_WORDS = (
    "type", "write", "write down", "dictate",                   # English
    "اكتب", "أكتب", "اطبع", "دون",                                # Arabic
    "ecris", "écris", "tape", "escribe", "escribir",            # French / Spanish
    "schreib", "schreibe", "scrivi", "escreva",                 # German / Italian / Portuguese
    "yaz", "напиши", "печатай", "введи",                        # Turkish / Russian
    "بنویس", "تایپ کن", "لکھو", "लिखो", "टाइप करो",                # Persian / Urdu / Hindi
    "输入", "打字", "入力", "타이핑", "입력", "พิมพ์",                 # Chinese / Japanese / Korean / Thai
)

# "Press enter" is its own command: typed text can never contain a new line, so sending one has to
# be asked for by name.
ENTER_WORDS = (
    "enter", "return", "send", "ادخال", "إدخال", "ارسل", "أرسل", "انتر", "entree", "entrée",
    "intro", "eingabe", "invio", "ввод", "энтер", "enter tusu", "엔터", "回车", "エンター",
)

# "Play <name>" reaches the same list, because that is how one asks for a place rather than a song.
# On its own, or with a name that is not on the list, it stays a media key: "play" still means play.
PLAY_WORDS = (
    "play", "open", "put on",                       # English
    "شغل", "شغلي", "افتح", "حط",                     # Arabic
    "joue", "lance", "reproduce", "pon",            # French / Spanish
    "spiel", "spiele", "riproduci", "toca",         # German / Italian / Portuguese
    "çal", "oynat", "включи", "поставь",            # Turkish / Russian
    "پخش کن", "چلاو", "चलाओ", "बजाओ",                 # Persian / Urdu / Hindi
    "播放", "打开", "再生", "재생", "เล่น",              # Chinese / Japanese / Korean / Thai
)

# The user's own Windows folders. The name is what you say; the path comes from Windows itself.
FOLDER_WORDS = {
    "desktop": ("desktop", "the desktop", "سطح المكتب", "المكتب", "bureau", "escritorio",
                "schreibtisch", "рабочий стол", "डेस्कटॉप", "桌面", "デスクトップ", "바탕화면"),
    "documents": ("documents", "document", "my documents", "المستندات", "الوثائق", "الملفات",
                  "documentos", "dokumente", "документы", "दस्तावेज़", "文档", "書類", "문서"),
    "downloads": ("downloads", "download", "my downloads", "التنزيلات", "التحميلات", "المحملات",
                  "descargas", "telechargements", "téléchargements", "downloads ordner",
                  "загрузки", "डाउनलोड", "下载", "ダウンロード", "다운로드"),
    "music": ("music", "my music", "songs", "الموسيقى", "الموسيقا", "الاغاني", "musique", "musica",
              "música", "musik", "музыка", "संगीत", "音乐", "音楽", "음악"),
    "pictures": ("pictures", "picture", "photos", "images", "الصور", "صور", "fotos", "bilder",
                 "изображения", "фото", "तस्वीरें", "图片", "画像", "사진"),
    "videos": ("videos", "video", "movies", "الفيديو", "الفيديوهات", "الافلام", "videos ordner",
               "vidéos", "видео", "वीडियो", "视频", "動画", "비디오"),
    "home": ("home", "my folder", "user folder", "المجلد الرئيسي", "مجلدي", "الرئيسيه",
             "accueil", "startseite", "домой", "домашняя папка", "होम", "主目录", "ホーム", "홈"),
}

CAPTION_WORDS = (
    "captions", "caption", "subtitles", "subtitle", "text", "box",  # English (the caption box)
    "الترجمه", "الترجمات", "النص", "الصندوق", "المربع",          # Arabic
    "sous titres", "les sous titres",                        # French
    "subtitulos", "subtítulos",                              # Spanish
    "untertitel",                                            # German
    "sottotitoli",                                           # Italian
    "legendas",                                              # Portuguese
    "altyazi", "altyazı", "altyazilari",                     # Turkish
    "субтитры", "субтитров",                                 # Russian
    "زیرنویس",                                                # Persian
    "سب ٹائٹل",                                               # Urdu
    "सबटाइटल", "उपशीर्षक", "अनुवाद",                             # Hindi
    "teks", "subtitel",                                      # Indonesian / Malay
    "字幕",                                                   # Chinese / Japanese
    "자막",                                                   # Korean
)

# Each caption action and the words that ask for it. The first word found in the sentence wins.
CAPTION_ACTIONS = (
    ("pause_captions", ("pause", "stop", "halt", "اوقف", "ايقاف", "وقف", "pause les", "arrete", "arrête",
                        "detén", "deten", "pausa", "anhalten", "stopp", "duraklat", "durdur",
                        "останови", "пауза", "متوقف کن", "روکو", "रोको", "बंद करो", "बंद कर", "jeda", "طفي", "اطفي",
                        "暂停", "暫停",
                        "一時停止", "止めて", "정지", "멈춰")),
    ("resume_captions", ("resume", "continue", "keep going", "تابع", "استانف", "كمل", "اشتغل",
                         "شغل الترجمه",
                         "reprends", "continue les", "reanuda", "continua", "continúa", "fortsetze",
                         "weiter", "devam", "возобнови", "продолжи", "ادامه بده", "जारी रखो",
                         "lanjutkan", "继续", "繼續", "再開", "계속")),
    ("hide_captions", ("hide", "اخف", "خبي", "cache", "oculta", "esconde", "verstecke", "ausblenden",
                       "nascondi", "esconder", "gizle", "скрой", "спрячь", "پنهان کن", "छुपाओ",
                       "sembunyikan", "隐藏", "隱藏", "非表示", "숨겨")),
    ("show_captions", ("show", "اظهر", "ارجع", "affiche", "montre", "muestra", "zeige", "einblenden",
                       "mostra", "mostrar", "goster", "göster", "покажи", "نشان بده", "दिखाओ",
                       "tampilkan", "显示", "顯示", "表示", "보여")),
    ("clear_captions", ("clear", "امسح", "نظف", "efface", "borra", "limpia", "losche", "lösche",
                        "cancella", "limpar", "temizle", "очисти", "сотри", "پاک کن", "साफ करो",
                        "bersihkan", "清除", "クリア", "消して", "지워")),
)

# Scripts that are written without spaces, so their words are matched as plain text.
NO_SPACE_RANGES = (
    (0x2E80, 0x9FFF),    # CJK radicals, kana, ideographs
    (0xA960, 0xA97F),    # Hangul jamo extended
    (0xAC00, 0xD7FF),    # Hangul syllables
    (0xF900, 0xFAFF),    # CJK compatibility ideographs
    (0x0E00, 0x0E7F),    # Thai
)
