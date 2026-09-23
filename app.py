import json
import uuid
from datetime import date

import streamlit as st


st.set_page_config(
    page_title="AI Sana — Challenge Hub",
    page_icon="✨",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem; }
      [data-testid="stAppViewContainer"] { background: #f5f7fb; }
      [data-testid="stSidebar"] { background: #101b35; }
      [data-testid="stSidebar"] * { color: #eef3ff !important; }
      h1, h2, h3 { color: #14213d; }
      .hero { background: linear-gradient(120deg,#14213d,#234d84); padding: 1.5rem 1.8rem;
              border-radius: 18px; color: white; margin-bottom: 1.2rem; }
      .hero h1 { color: white; margin: 0; }
      .hero p { color: #dce8ff; margin: .4rem 0 0 0; }
      .muted { color: #62708a; }
      .small-note { color: #62708a; font-size: .88rem; }
      .tag { display:inline-block; padding:.25rem .6rem; border-radius:999px;
             background:#e6edfb; color:#22467d; font-size:.82rem; margin-right:.3rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


SCORING_RULES = [
    ("Контекст и потребность", 20, ("context", "need")),
    ("Данные и материалы", 20, ("available_data",)),
    ("Ожидаемый результат", 15, ("expected_result",)),
    ("Критерии успеха", 15, ("success_criteria",)),
    ("Ограничения", 10, ("constraints",)),
    ("Пользователи", 10, ("users",)),
    ("Связь с бизнесом", 10, ("contact", "interaction_format")),
]

FIELD_LABELS = {
    "context": "Что происходит сейчас?",
    "need": "Что нужно изменить?",
    "available_data": "Какие данные и материалы доступны?",
    "expected_result": "Какой результат должна подготовить команда?",
    "success_criteria": "По каким признакам поймём, что решение удалось?",
    "constraints": "Какие есть сроки, технологии или другие ограничения?",
    "users": "Для кого создаётся решение?",
    "contact": "Кто будет контактным лицом от бизнеса?",
    "interaction_format": "Как команда сможет получать обратную связь?",
}

QUESTION_TEMPLATES = {
    "context": "Что происходит сейчас и в чём именно проявляется проблема?",
    "need": "Что должно измениться после решения этой задачи?",
    "available_data": "Какие данные, примеры или материалы вы сможете предоставить команде?",
    "expected_result": "Какой конкретный результат вы ждёте от команды к концу работы?",
    "success_criteria": "По каким измеримым признакам вы примете результат?",
    "constraints": "Какие сроки, технологии, доступы или другие ограничения нужно учесть?",
    "users": "Кто будет пользоваться результатом решения?",
    "contact": "Кто со стороны бизнеса сможет отвечать на вопросы команды?",
    "interaction_format": "Как часто и в каком формате команда сможет получать обратную связь?",
}

AI_SYSTEM_PROMPT = """Ты помощник AI Sana Challenge Hub.
Проверь, каких сведений не хватает в описании бизнес-задачи.
Верни только JSON вида {"questions": ["вопрос 1", "вопрос 2", "вопрос 3"]}.
Не добавляй факты, которых нет во входных данных. Задай минимум три уместных вопроса."""


def score_task(task):
    """Возвращает прозрачный рейтинг только по заполненным и подтверждённым полям."""
    confirmed = set(task.get("confirmed_fields", []))
    total = 0
    breakdown = []
    missing = []

    for title, points, fields in SCORING_RULES:
        per_field = points / len(fields)
        earned = 0
        for field in fields:
            if task.get(field, "").strip() and field in confirmed:
                earned += per_field
            else:
                missing.append(FIELD_LABELS[field])
        earned = int(round(earned))
        total += earned
        breakdown.append({"Критерий": title, "Получено": earned, "Максимум": points})

    return min(int(total), 100), breakdown, list(dict.fromkeys(missing))


def readiness_label(score):
    if score < 40:
        return "Черновик", "Задача видна в каталоге, но требует уточнения"
    if score < 70:
        return "Рабочая", "Команды могут откликаться; задачу можно рекомендовать"
    if score < 90:
        return "Готовая", "Задача получает более высокую позицию в каталоге"
    return "Приоритетная", "Задача почти полностью готова к работе"


def make_title(description):
    line = (description or "").strip().splitlines()[0].strip()
    if not line:
        return "Новая бизнес-задача"
    return line if len(line) <= 72 else line[:69].rstrip() + "…"


def local_ai_questions(task):
    """Локальная AI-демонстрация: анализирует пропуски, проверяет формат, имеет fallback."""
    prompt_input = {
        key: task.get(key, "")
        for key in ("title", "context", "need", "available_data", "expected_result",
                    "success_criteria", "constraints", "users", "contact", "interaction_format")
    }
    prompt = AI_SYSTEM_PROMPT + "\nВходные данные:\n" + json.dumps(prompt_input, ensure_ascii=False)

    try:
        questions = [
            QUESTION_TEMPLATES[field]
            for field in FIELD_LABELS
            if not task.get(field, "").strip()
        ]
        if len(questions) < 3:
            questions.extend([
                "Какой результат будет наиболее полезен бизнесу в первую очередь?",
                "Есть ли пример похожего решения или процесса, на который можно ориентироваться?",
                "Кто подтвердит, что подготовленный результат соответствует ожиданиям?",
            ])
        response = {"questions": list(dict.fromkeys(questions))[:5]}

        # В реальном API здесь проверялся бы ответ модели. Локальный режим использует ту же проверку.
        if not isinstance(response, dict):
            raise ValueError("Ответ должен быть объектом JSON")
        if not isinstance(response.get("questions"), list):
            raise ValueError("В ответе нет списка questions")
        if not all(isinstance(item, str) and item.strip() for item in response["questions"]):
            raise ValueError("Вопросы должны быть непустыми строками")
        if len(response["questions"]) < 3:
            raise ValueError("Нужно не менее трёх вопросов")
        return response["questions"], prompt, "локальный режим"

    except (TypeError, ValueError, KeyError):
        fallback = [
            "Что происходит сейчас и что необходимо изменить?",
            "Какие данные или материалы доступны команде?",
            "Как бизнес поймёт, что результат подходит?",
        ]
        return fallback, prompt, "резервный ответ после ошибки формата"


def make_demo_tasks():
    examples = [
        {
            "title": "Сократить время оформления заказа на складе",
            "industry": "Логистика и склад",
            "context": "Сотрудники вручную сверяют заявки, остатки и товары в пути; часть заказов приходится пересчитывать.",
            "need": "Подготовить понятную рекомендацию по пополнению склада на основе регулярного спроса.",
            "users": "Менеджеры закупа и склада",
            "available_data": "Есть CSV с продажами за год, остатками и открытыми заказами.",
            "expected_result": "Прототип таблицы или сервиса с рекомендуемыми заказами поставщикам.",
            "success_criteria": "На тестовой выборке рекомендации не включают разовые всплески продаж и показывают расчёт.",
            "constraints": "Прототип должен работать на локальном ноутбуке; срок — 5 недель.",
            "contact": "Руководитель отдела закупа",
            "interaction_format": "Еженедельная встреча и ответы на вопросы в рабочем чате.",
        },
        {
            "title": "Находить повторяющиеся обращения клиентов",
            "industry": "Телеком",
            "context": "Операторы вручную просматривают обращения и поздно замечают повторяющиеся проблемы.",
            "need": "Группировать похожие обращения, чтобы быстрее находить частые причины жалоб.",
            "users": "Руководители контакт-центра",
            "available_data": "Можно предоставить обезличенные примеры обращений в CSV.",
            "expected_result": "Демонстрационный экран с группами похожих обращений.",
            "success_criteria": "Сотрудник может проверить группу и понять, по каким словам обращения объединены.",
            "constraints": "Персональные данные клиентов использовать нельзя.",
            "contact": "Менеджер клиентского сервиса",
            "interaction_format": "Две консультации в неделю по видеосвязи.",
        },
        {
            "title": "Уменьшить потери тепла в учебных корпусах",
            "industry": "Образование",
            "context": "В нескольких корпусах отопление регулируется вручную, а данные о температуре хранятся разрозненно.",
            "need": "Понять, где возникают перепады температуры и какие меры стоит проверить.",
            "users": "Административная и эксплуатационная команды",
            "available_data": "Есть ежечасные показания датчиков за два зимних месяца.",
            "expected_result": "Дашборд с аномалиями и списком приоритетных зон.",
            "success_criteria": "",
            "constraints": "Нельзя управлять оборудованием напрямую; только анализ и рекомендации.",
            "contact": "Специалист по эксплуатации",
            "interaction_format": "",
        },
        {
            "title": "Упростить поиск нужной услуги на сайте",
            "industry": "Цифровые сервисы",
            "context": "Пользователи не всегда понимают, какой раздел сайта отвечает за их вопрос.",
            "need": "Предложить более быстрый путь от вопроса пользователя до нужной услуги.",
            "users": "Посетители сайта",
            "available_data": "",
            "expected_result": "Кликабельный прототип нового сценария поиска.",
            "success_criteria": "",
            "constraints": "Для демонстрации использовать только открытые страницы сайта.",
            "contact": "",
            "interaction_format": "",
        },
        {
            "title": "Хотим улучшить продажи с помощью AI",
            "industry": "Розничная торговля",
            "context": "Бизнес хочет понять, как применить AI для улучшения продаж.",
            "need": "",
            "users": "",
            "available_data": "",
            "expected_result": "",
            "success_criteria": "",
            "constraints": "",
            "contact": "",
            "interaction_format": "",
        },
    ]

    tasks = []
    for index, example in enumerate(examples, start=1):
        example["id"] = "demo-task-" + str(index)
        example["source_text"] = example["context"]
        example["status"] = "published"
        example["created_by"] = "Демо-бизнес"
        example["confirmed_fields"] = [
            field for field in FIELD_LABELS if example.get(field, "").strip()
        ]
        example["score"] = score_task(example)[0]
        tasks.append(example)
    return tasks


def make_demo_teams():
    return [
        {"id": "team-1", "name": "OneShot", "interests": ["Логистика и склад", "AI"],
         "skills": ["Python", "аналитика данных", "Streamlit"], "points": 0},
        {"id": "team-2", "name": "Data Nomads", "interests": ["Телеком", "AI"],
         "skills": ["NLP", "Python", "дашборды"], "points": 0},
        {"id": "team-3", "name": "Qadam Lab", "interests": ["Образование", "экология"],
         "skills": ["аналитика", "дизайн", "прототипирование"], "points": 0},
        {"id": "team-4", "name": "Steppe Coders", "interests": ["Цифровые сервисы", "AI"],
         "skills": ["frontend", "UX", "Python"], "points": 0},
        {"id": "team-5", "name": "Green Byte", "interests": ["Образование", "экология"],
         "skills": ["данные", "визуализация", "Python"], "points": 0},
    ]


def make_demo_proposals():
    return [
        {"id": "proposal-1", "task_id": "demo-task-1", "team_id": "team-1",
         "idea": "Сделать расчёт регулярного спроса и рекомендовать объёмы пополнения.",
         "plan": "Очистить CSV, убрать аномальные всплески, собрать простой экран рекомендаций.",
         "deadline": "5 недель", "link": "https://github.com/", "status": "Ожидает решения",
         "milestones": []},
        {"id": "proposal-2", "task_id": "demo-task-2", "team_id": "team-2",
         "idea": "Сравнивать обращения по смыслу и показывать повторяющиеся темы.",
         "plan": "Подготовить обезличенные примеры, сгруппировать тексты, показать объяснения групп.",
         "deadline": "4 недели", "link": "https://github.com/", "status": "Ожидает решения",
         "milestones": []},
        {"id": "proposal-3", "task_id": "demo-task-3", "team_id": "team-5",
         "idea": "Выделить зоны с частыми перепадами и сравнить их по времени.",
         "plan": "Проверить данные датчиков, визуализировать аномалии, обсудить меры с эксплуатацией.",
         "deadline": "4 недели", "link": "https://github.com/", "status": "Ожидает решения",
         "milestones": []},
        {"id": "proposal-4", "task_id": "demo-task-4", "team_id": "team-4",
         "idea": "Проверить понятность навигации и собрать короткий сценарий поиска услуги.",
         "plan": "Выбрать типовые вопросы, нарисовать путь пользователя, собрать кликабельный прототип.",
         "deadline": "3 недели", "link": "https://github.com/", "status": "Ожидает решения",
         "milestones": []},
        {"id": "proposal-5", "task_id": "demo-task-5", "team_id": "team-2",
         "idea": "Сначала выяснить доступные данные и определить измеримую цель.",
         "plan": "Провести короткую консультацию, после неё предложить безопасный демонстрационный сценарий.",
         "deadline": "2 недели", "link": "https://github.com/", "status": "Ожидает решения",
         "milestones": []},
    ]


def init_state():
    if "tasks" not in st.session_state:
        st.session_state.tasks = make_demo_tasks()
    if "teams" not in st.session_state:
        st.session_state.teams = make_demo_teams()
    if "proposals" not in st.session_state:
        st.session_state.proposals = make_demo_proposals()


init_state()


def task_by_id(task_id):
    return next((task for task in st.session_state.tasks if task["id"] == task_id), None)


def team_by_id(team_id):
    return next((team for team in st.session_state.teams if team["id"] == team_id), None)


def render_hero():
    st.markdown(
        '<div class="hero"><h1>AI Sana Challenge Hub</h1>'
        '<p>От бизнес-идеи до задачи, отклика команды и решения бизнеса</p></div>',
        unsafe_allow_html=True,
    )


def render_overview():
    render_hero()
    total = len(st.session_state.tasks)
    open_tasks = sum(task["status"] == "published" for task in st.session_state.tasks)
    pending = sum(item["status"] == "Ожидает решения" for item in st.session_state.proposals)
    average = round(sum(score_task(task)[0] for task in st.session_state.tasks) / max(total, 1))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Задач в демо-каталоге", total)
    col2.metric("Опубликовано", open_tasks)
    col3.metric("Ожидают решения", pending)
    col4.metric("Средняя готовность", str(average) + "/100")

    st.subheader("Как пройти демонстрацию")
    steps = [
        ("1", "Бизнес", "Создайте слабый черновик, ответьте на вопросы и подтвердите карточку."),
        ("2", "Рейтинг", "Покажите, какие подтверждённые сведения добавили баллы."),
        ("3", "Каталог", "Откройте задачу командам; даже незрелые задачи не скрываются."),
        ("4", "Отклик", "Команда отправляет план, срок и ссылку на прототип."),
        ("5", "Решение", "Бизнес вручную принимает или отклоняет предложения."),
    ]
    for number, title, description in steps:
        with st.container(border=True):
            st.markdown("**" + number + " · " + title + "**")
            st.write(description)

    st.caption("Демо работает без аккаунтов и внешней AI-подписки. Данные хранятся в текущей сессии браузера.")


def render_business():
    st.title("Рабочее место бизнеса")
    st.write("Опишите задачу, дополните карточку и опубликуйте её для студенческих команд.")

    with st.expander("Создать черновик из короткого описания", expanded=True):
        with st.form("new_task_form"):
            raw_text = st.text_area(
                "Опишите потребность своими словами",
                placeholder="Например: хотим сократить время обработки обращений клиентов",
                height=110,
            )
            industry = st.selectbox(
                "Отрасль",
                ["Розничная торговля", "Телеком", "Логистика и склад", "Образование",
                 "Цифровые сервисы", "Энергетика", "Другое"],
            )
            create = st.form_submit_button("Подготовить черновик и вопросы", type="primary")

        if create:
            if not raw_text.strip():
                st.error("Введите короткое описание задачи.")
            else:
                new_id = "task-" + uuid.uuid4().hex[:8]
                task = {
                    "id": new_id,
                    "title": make_title(raw_text),
                    "industry": industry,
                    "context": raw_text.strip(),
                    "need": "",
                    "users": "",
                    "available_data": "",
                    "expected_result": "",
                    "success_criteria": "",
                    "constraints": "",
                    "contact": "",
                    "interaction_format": "",
                    "source_text": raw_text.strip(),
                    "confirmed_fields": [],
                    "status": "draft",
                    "created_by": "Бизнес",
                }
                task["score"] = score_task(task)[0]
                st.session_state.tasks.insert(0, task)
                st.session_state.edit_task_id = new_id
                st.success("Черновик создан. Ответьте на вопросы и подтвердите сведения ниже.")
                st.rerun()

    if not st.session_state.tasks:
        st.info("Задач пока нет.")
        return

    selected_id = st.selectbox(
        "Выберите задачу для редактирования",
        options=[task["id"] for task in st.session_state.tasks],
        format_func=lambda task_id: task_by_id(task_id)["title"],
        key="edit_task_id",
    )
    task = task_by_id(selected_id)
    score, breakdown, missing = score_task(task)
    label, description = readiness_label(score)

    left, right = st.columns([1, 2])
    with left:
        st.metric("Рейтинг готовности", str(score) + "/100", label)
        st.caption(description)
        st.progress(score / 100)
    with right:
        st.write("**Чего ещё не хватает**")
        if missing:
            for item in missing[:5]:
                st.write("• " + item)
        else:
            st.success("Все критерии рейтинга заполнены и подтверждены.")

    questions, prompt, ai_mode = local_ai_questions(task)
    with st.expander("AI-уточнения · " + ai_mode, expanded=True):
        st.write("По описанию и незаполненным полям стоит уточнить:")
        for question in questions:
            st.write("• " + question)
        st.caption("AI-демо не добавляет сведения в карточку. Ответы вносит и подтверждает представитель бизнеса.")
        with st.expander("Промпт, вход и проверка формата"):
            st.code(prompt, language="text")
            st.caption('Ожидаемый формат ответа: {"questions": ["вопрос 1", "вопрос 2", "вопрос 3"]}. '
                       "Если формат неправильный, включается безопасный резервный список вопросов.")

    with st.form("edit_task_form"):
        st.subheader("Редактируемая карточка")
        title = st.text_input("Название задачи", value=task.get("title", ""))
        context = st.text_area("Контекст: что происходит сейчас?", value=task.get("context", ""))
        need = st.text_area("Потребность: что нужно изменить?", value=task.get("need", ""))
        users = st.text_input("Для кого создаётся решение?", value=task.get("users", ""))
        available_data = st.text_area(
            "Данные и материалы, доступные команде", value=task.get("available_data", "")
        )
        expected_result = st.text_area(
            "Ожидаемый результат работы команды", value=task.get("expected_result", "")
        )
        success_criteria = st.text_area(
            "Измеримые критерии успеха", value=task.get("success_criteria", "")
        )
        constraints = st.text_area(
            "Сроки, технологии, доступы и другие ограничения", value=task.get("constraints", "")
        )
        contact = st.text_input("Контактное лицо со стороны бизнеса", value=task.get("contact", ""))
        interaction_format = st.text_input(
            "Формат взаимодействия и обратной связи",
            value=task.get("interaction_format", ""),
        )
        confirm_details = st.checkbox("Подтверждаю заполненные сведения")
        publish = st.checkbox(
            "Опубликовать задачу в общем каталоге",
            value=task.get("status") == "published",
        )
        save = st.form_submit_button("Сохранить карточку", type="primary")

    if save:
        values = {
            "title": title.strip(),
            "context": context.strip(),
            "need": need.strip(),
            "users": users.strip(),
            "available_data": available_data.strip(),
            "expected_result": expected_result.strip(),
            "success_criteria": success_criteria.strip(),
            "constraints": constraints.strip(),
            "contact": contact.strip(),
            "interaction_format": interaction_format.strip(),
        }
        old_confirmed = set(task.get("confirmed_fields", []))
        if confirm_details:
            confirmed = [field for field, value in values.items() if value]
        else:
            confirmed = [
                field for field in old_confirmed
                if values.get(field, "") == task.get(field, "") and values.get(field, "")
            ]
        task.update(values)
        task["confirmed_fields"] = confirmed
        task["status"] = "published" if publish else "draft"
        task["score"] = score_task(task)[0]
        st.success("Карточка сохранена. Подтверждённые поля учтены в рейтинге.")
        st.rerun()

    st.subheader("Расшифровка рейтинга")
    st.dataframe(breakdown, use_container_width=True, hide_index=True)


def render_catalog():
    st.title("Каталог задач для команд")
    st.write("Все опубликованные задачи доступны для просмотра. Низкий рейтинг показывает, что задачу стоит уточнить.")
    tasks = [task for task in st.session_state.tasks if task["status"] == "published"]
    if not tasks:
        st.info("Пока нет опубликованных задач. Бизнес может опубликовать задачу в разделе «Рабочее место бизнеса».")
        return

    team_ids = [team["id"] for team in st.session_state.teams]
    team_id = st.selectbox(
        "Представитель команды",
        team_ids,
        format_func=lambda key: team_by_id(key)["name"],
        key="catalog_team",
    )
    team = team_by_id(team_id)

    topics = ["Все темы"] + sorted(set(task["industry"] for task in tasks))
    topic = st.selectbox("Тема", topics)
    if topic != "Все темы":
        tasks = [task for task in tasks if task["industry"] == topic]

    readiness_options = ["Все уровни", "Черновик", "Рабочая", "Готовая", "Приоритетная"]
    selected_readiness = st.selectbox("Уровень готовности", readiness_options)
    if selected_readiness != "Все уровни":
        tasks = [
            task for task in tasks
            if readiness_label(score_task(task)[0])[0] == selected_readiness
        ]

    tasks = sorted(tasks, key=lambda item: score_task(item)[0], reverse=True)
    st.caption("Команда: " + team["name"] + " · Интересы: " + ", ".join(team["interests"]))
    st.caption("Каталог открыт полностью: рекомендации не ограничивают просмотр задач.")

    for task in tasks:
        score, _, missing = score_task(task)
        label, _ = readiness_label(score)
        with st.container(border=True):
            title_col, score_col = st.columns([4, 1])
            title_col.subheader(task["title"])
            score_col.metric("Готовность", str(score) + "/100")
            st.markdown(
                '<span class="tag">' + task["industry"] + "</span>"
                '<span class="tag">' + label + "</span>",
                unsafe_allow_html=True,
            )
            st.write(task.get("context", "Контекст пока не добавлен."))
            if missing:
                st.caption("Нужно уточнить: " + "; ".join(missing[:3]))
            idea = task["industry"] in team["interests"] or "AI" in team["interests"]
            if idea:
                st.caption("Похоже на интересы команды: " + team["name"] + " · совпала тема задачи.")
            else:
                st.caption("Команда может откликнуться, даже если задача не входит в её интересы.")

    st.divider()
    st.subheader("Отправить предложение")
    options = [task["id"] for task in tasks]
    selected_task = st.selectbox(
        "Выберите задачу",
        options,
        format_func=lambda key: task_by_id(key)["title"],
        key="proposal_task",
    )
    with st.form("proposal_form"):
        idea = st.text_area("Идея решения")
        plan = st.text_area("Краткий план работы")
        deadline = st.text_input("Предполагаемый срок")
        link = st.text_input("Ссылка на прототип или материалы (если есть)")
        send = st.form_submit_button("Отправить предложение", type="primary")
    if send:
        if not idea.strip() or not plan.strip() or not deadline.strip():
            st.error("Заполните идею, план и срок.")
        else:
            st.session_state.proposals.append({
                "id": "proposal-" + uuid.uuid4().hex[:8],
                "task_id": selected_task,
                "team_id": team_id,
                "idea": idea.strip(),
                "plan": plan.strip(),
                "deadline": deadline.strip(),
                "link": link.strip() or "Не указана",
                "status": "Ожидает решения",
                "milestones": [],
            })
            st.success("Предложение отправлено бизнесу.")
            st.rerun()


def render_responses():
    st.title("Отклики и решение бизнеса")
    tasks_with_proposals = [
        task for task in st.session_state.tasks
        if any(item["task_id"] == task["id"] for item in st.session_state.proposals)
    ]
    if not tasks_with_proposals:
        st.info("Пока нет задач с предложениями команд.")
        return

    selected_id = st.selectbox(
        "Задача",
        [task["id"] for task in tasks_with_proposals],
        format_func=lambda key: task_by_id(key)["title"],
    )
    selected_task = task_by_id(selected_id)
    st.subheader(selected_task["title"])

    proposals = [item for item in st.session_state.proposals if item["task_id"] == selected_id]
    for proposal in proposals:
        team = team_by_id(proposal["team_id"])
        with st.container(border=True):
            st.markdown("### " + team["name"] + " · " + proposal["status"])
            st.write("**Идея:** " + proposal["idea"])
            st.write("**План:** " + proposal["plan"])
            st.write("**Срок:** " + proposal["deadline"])
            st.write("**Ссылка:** " + proposal["link"])
            col1, col2 = st.columns(2)
            if proposal["status"] == "Ожидает решения":
                if col1.button("Выбрать команду", key="accept-" + proposal["id"], type="primary"):
                    proposal["status"] = "Выбрана бизнесом"
                    st.rerun()
                if col2.button("Отклонить", key="reject-" + proposal["id"]):
                    proposal["status"] = "Отклонено бизнесом"
                    st.rerun()
            elif proposal["status"] == "Выбрана бизнесом":
                st.success("Бизнес выбрал эту команду. Решение принято вручную.")
                with st.form("milestone-" + proposal["id"]):
                    milestone = st.text_input("Какой этап команда фактически выполнила?")
                    confirm = st.form_submit_button("Подтвердить этап и начислить 1 балл")
                if confirm:
                    if milestone.strip():
                        proposal.setdefault("milestones", []).append(milestone.strip())
                        team["points"] += 1
                        st.success("Этап подтверждён. Команде начислен 1 балл.")
                        st.rerun()
                    else:
                        st.error("Опишите выполненный этап перед подтверждением.")

    st.divider()
    st.subheader("Очки команд за подтверждённый прогресс")
    ranking = sorted(st.session_state.teams, key=lambda item: item["points"], reverse=True)
    st.dataframe(
        [{"Команда": team["name"], "Подтверждённые баллы": team["points"]} for team in ranking],
        use_container_width=True,
        hide_index=True,
    )


def render_team_profiles():
    st.title("Профили студенческих команд")
    st.write("Профили помогают бизнесу понять интересы и навыки откликнувшихся команд.")
    for team in st.session_state.teams:
        with st.container(border=True):
            st.subheader(team["name"])
            st.write("**Интересы:** " + ", ".join(team["interests"]))
            st.write("**Навыки:** " + ", ".join(team["skills"]))
            st.write("**Баллы за подтверждённый прогресс:** " + str(team["points"]))


with st.sidebar:
    st.markdown("## AI Sana")
    page = st.radio(
        "Раздел",
        ["Обзор", "Рабочее место бизнеса", "Каталог для команд", "Отклики бизнеса", "Профили команд"],
    )
    st.divider()
    st.caption("Локальный MVP · синтетические демонстрационные данные")


if page == "Обзор":
    render_overview()
elif page == "Рабочее место бизнеса":
    render_business()
elif page == "Каталог для команд":
    render_catalog()
elif page == "Отклики бизнеса":
    render_responses()
else:
    render_team_profiles()
