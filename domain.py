"""Pure business rules. No external dependencies or network access."""
import json
import re
from urllib.parse import urlparse

FIELDS = {
    "title": "Атауы", "context": "Контекст", "need": "Қажеттілік",
    "users": "Пайдаланушылар", "data": "Деректер мен материалдар",
    "constraints": "Шектеулер", "outcome": "Күтілетін нәтиже",
    "success": "Табыс критерийлері", "contact": "Байланыс",
    "interaction": "Өзара әрекеттесу форматы",
}
TOPICS = ["Сауда", "Білім", "Экология", "Логистика", "Агро"]
GROUPS = [
    ("Контекст және қажеттілік", [("context", 10), ("need", 10)]),
    ("Деректер мен материалдар", [("data", 20)]),
    ("Күтілетін нәтиже", [("outcome", 15)]),
    ("Табыс критерийлері", [("success", 15)]),
    ("Шектеулер", [("constraints", 10)]),
    ("Пайдаланушылар", [("users", 10)]),
    ("Бизнеспен байланыс", [("contact", 5), ("interaction", 5)]),
]
LIMITS = {"title": 4, "context": 12, "need": 12, "users": 8, "data": 12,
          "constraints": 8, "outcome": 12, "success": 12, "contact": 5, "interaction": 10}
MILESTONES = {"research": ("Мәселені зерттеу", 20), "prototype": ("Прототип", 30), "validation": ("Нәтижені тексеру", 50)}

class ValidationError(ValueError):
    pass

def text_value(value, label, minimum=0, maximum=4000):
    if not isinstance(value, str):
        raise ValidationError(f"{label}: мәтін енгізіңіз.")
    value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise ValidationError(f"{label}: {minimum}–{maximum} таңба болуы керек.")
    return value

def valid_url(value):
    try:
        p = urlparse(value)
        return p.scheme in ("http", "https") and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False

def field_issue(key, value):
    value = value.strip()
    if len(value) < LIMITS[key]:
        return f"Кемінде {LIMITS[key]} таңбамен нақтылаңыз"
    if value.lower() in {"белгісіз", "жоқ", "unknown", "none", "анықталмаған"}:
        return "Нақты мәлімет енгізіңіз"
    if key == "success" and not re.search(r"\d", value):
        return "Сандық мақсат қосыңыз: мысалы, 30% немесе 5 сынақ"
    if key == "contact" and not (re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) or (re.search(r"\+?[\d ()-]{10,}", value) and len(re.sub(r"\D", "", value)) >= 10)):
        return "Email немесе телефон нөмірін енгізіңіз"
    return ""

def level(score):
    if score < 40: return {"key": "draft", "label": "Жоба", "range": "0–39"}
    if score < 70: return {"key": "working", "label": "Жұмыс", "range": "40–69"}
    if score < 90: return {"key": "ready", "label": "Дайын", "range": "70–89"}
    return {"key": "priority", "label": "Басым", "range": "90–100"}

def rating(fields, confirmed):
    groups, missing, total = [], [], 0
    for label, entries in GROUPS:
        earned = 0
        for key, weight in entries:
            issue = field_issue(key, fields.get(key, ""))
            if not issue and key not in confirmed:
                issue = "Мәліметті оқып, растаңыз"
            if issue:
                missing.append({"field": key, "label": FIELDS[key], "points": weight, "reason": issue})
            else:
                earned += weight
        maximum = sum(weight for _, weight in entries)
        groups.append({"label": label, "earned": earned, "maximum": maximum})
        total += earned
    return {"score": total, "level": level(total), "groups": groups, "missing": missing}

def clean_card(body, require_title=True):
    if not isinstance(body, dict): raise ValidationError("JSON объектісі қажет.")
    source = body.get("fields")
    if not isinstance(source, dict): raise ValidationError("Карточка өрістері қажет.")
    fields = {key: text_value(source.get(key, ""), label, maximum=180 if key == "title" else 4000) for key, label in FIELDS.items()}
    if require_title and field_issue("title", fields["title"]): raise ValidationError("Атауы кемінде 4 таңба болуы керек.")
    topic = body.get("topic")
    if topic not in TOPICS: raise ValidationError("Саланы тізімнен таңдаңыз.")
    confirmed = body.get("confirmed", [])
    if not isinstance(confirmed, list) or any(not isinstance(k, str) or k not in FIELDS for k in confirmed):
        raise ValidationError("Расталған өрістер форматы дұрыс емес.")
    return fields, topic, sorted(set(confirmed))

QUESTIONS = {
    "title": "Міндетке қандай қысқа әрі нақты атау бересіз?",
    "context": "Қазір бұл жұмыс қалай орындалады және қандай қиындық бар?",
    "need": "Нақты нені өзгерткіңіз келеді?",
    "users": "Шешімді кімдер және қандай жағдайда қолданады?",
    "data": "Командаға қандай деректер, файлдар немесе мысалдар бере аласыз? Форматы мен көлемі қандай?",
    "constraints": "Мерзім, технология, бюджет немесе қолжетімділік бойынша қандай шектеулер бар?",
    "outcome": "Команда соңында қандай нақты өнімді тапсыруы керек?",
    "success": "Нәтижені қандай өлшенетін көрсеткішпен қабылдайсыз? Сан мен мақсатты мәнді жазыңыз.",
    "contact": "Байланыс үшін қандай email немесе телефон көрсетесіз?",
    "interaction": "Командамен қаншалықты жиі, қай арнада сөйлесесіз және кері байланыс қашан беріледі?",
}
DOMAIN_QUESTIONS = {
    "Сауда": "data", "Білім": "users", "Экология": "success", "Логистика": "constraints", "Агро": "data"
}

def ai_input(body):
    description = text_value(body.get("description"), "Сипаттама", 12, 6000)
    topic = body.get("topic")
    if topic not in TOPICS: raise ValidationError("Саланы таңдаңыз.")
    answers = body.get("answers", {})
    if not isinstance(answers, dict) or any(k not in FIELDS for k in answers):
        raise ValidationError("Жауаптар форматы дұрыс емес.")
    answers = {k: text_value(v, FIELDS[k], maximum=180 if k == "title" else 4000) for k, v in answers.items()}
    return description, topic, answers

def local_analysis(description, topic, answers):
    # Only exact user text enters the card; no inferred business facts.
    fields = {k: "" for k in FIELDS}
    fields["need"] = description[:4000]
    evidence = {"need": "description"}
    for key, value in answers.items():
        if value:
            fields[key] = value
            evidence[key] = f"answers.{key}"
    missing = [k for k in FIELDS if field_issue(k, fields[k])]
    preferred = DOMAIN_QUESTIONS[topic]
    keys = sorted(missing, key=lambda k: (k != preferred, list(FIELDS).index(k)))
    # Minimum three questions, even for complete input (verification questions).
    for key in ("success", "data", "constraints"):
        if len(keys) >= 3: break
        if key not in keys: keys.append(key)
    questions = [{"field": k, "question": f"{topic}: {QUESTIONS[k]}", "kind": "missing" if k in missing else "verify"} for k in keys]
    return {"fields": fields, "questions": questions, "missing": missing, "evidence": evidence}

def validate_ai_response(raw, description, topic, answers):
    """Reject malformed, incomplete or fabricated output at the adapter boundary."""
    try:
        result = json.loads(raw)
        expected = local_analysis(description, topic, answers)
        if not isinstance(result, dict) or set(result) != set(expected): raise ValueError()
        # Stub contract is deterministic; future provider must keep grounded fields.
        if result["fields"] != expected["fields"] or result["evidence"] != expected["evidence"]: raise ValueError()
        if result["missing"] != expected["missing"] or result["questions"] != expected["questions"]: raise ValueError()
        return result
    except (ValueError, TypeError, KeyError):
        raise ValidationError("AI жауабы келісімшартқа сай емес; қауіпсіз жергілікті нәтиже қолданылды.")

def analyze(body, provider=None):
    description, topic, answers = ai_input(body)
    warning = ""
    expected = local_analysis(description, topic, answers)
    try:
        raw = provider(body) if provider else json.dumps(expected, ensure_ascii=False)
        result = validate_ai_response(raw, description, topic, answers)
    except Exception:
        warning = "AI жауабы жарамсыз немесе қолжетімсіз. Қауіпсіз жергілікті талдау қолданылды."
        result = expected
    return {**result, "mode": "local_stub", "warning": warning,
            "notice": "Жергілікті AI-демо: ережелік талдау. Сыртқы модель шақырылмайды; фактілер тек сіздің мәтініңізден алынады."}
