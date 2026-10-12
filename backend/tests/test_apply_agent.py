"""El agente de aplicacion arma borradores sin inventar nada.

Las preguntas de los formularios de aqui estan copiadas de formularios reales
de Greenhouse (Canonical, Anthropic, Amplemarket, leidos el 2026-10-12), porque
los errores que importan salen de como los escriben de verdad: la pregunta de
viajes de Canonical que menciona visas, la politica de IA de Anthropic, las
preguntas de diversidad mezcladas con las normales.
"""

import json
from types import SimpleNamespace

import pytest

from app.services import anthropic_client
from app.services.apply_agent import draft as draft_mod
from app.services.apply_agent.classify import (
    KIND_CHOICE,
    KIND_CONSENT,
    KIND_IDENTITY,
    KIND_OPEN,
    KIND_PERSONAL,
    KIND_SALARY,
    KIND_SENSITIVE,
    KIND_WORK_AUTH,
    classify,
    mentions_ai_policy,
    question_core,
    topic_of,
)
from app.services.apply_agent.draft import FILLED, NEEDS_USER, SKIPPED, build_deterministic, build_draft
from app.services.apply_agent.facts import build_facts, missing_for_agent
from app.services.apply_agent.greenhouse import FormField, parse_form, parse_greenhouse_ref

CANONICAL_TRAVEL = (
    "We require all colleagues to meet in person 2-4 times a year, at internal company events lasting "
    "between 1-2 weeks. We try to pick new and interesting locations that will likely require international "
    "travel and entry requirement visas and vaccinations. Are you willing and able to commit to this?"
)


def _q(label, name, tipo="input_text", required=True, values=None):
    campo = {"name": name, "type": tipo}
    if values is not None:
        campo["values"] = [{"label": l, "value": v} for l, v in values]
    return {"label": label, "required": required, "fields": [campo]}


def _yes_no(label, name, required=True):
    return _q(label, name, "multi_value_single_select", required, [("Yes", "1"), ("No", "0")])


def _form_data(*extra, ai_policy=False, **kwargs):
    preguntas = [
        _q("First Name", "first_name"),
        _q("Last Name", "last_name"),
        _q("Email", "email"),
        _q("Phone", "phone", required=False),
        {
            "label": "Resume/CV",
            "required": True,
            "fields": [{"name": "resume", "type": "input_file"}, {"name": "resume_text", "type": "textarea"}],
        },
        _q("LinkedIn Profile", "question_1", required=False),
        *extra,
    ]
    if ai_policy:
        preguntas.append(
            _yes_no(
                "During this application process I agree to use only my own words. I understand that "
                "plagiarism, the use of AI or other generated content will disqualify my application.",
                "question_ai",
            )
        )
    data = {
        "title": "Backend Engineer",
        "company_name": "Acme",
        "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/123",
        "language": "en",
        "questions": preguntas,
        "location_questions": [],
        "compliance": [],
        "demographic_questions": None,
    }
    data.update(kwargs)
    return data


PROFILE = {
    "contact_info": {
        "phone": "+1 809 555 0100",
        "city": "Santiago",
        "country": "República Dominicana",
        "linkedin": "https://linkedin.com/in/ana",
        "github": "https://github.com/ana",
    },
    "headline": "Backend developer",
    "experience": [
        {"company": "Old Co", "title": "Intern", "start_date": "2023-01", "end_date": "2023-06", "bullets": ["Did X"]},
        {"company": "Now Co", "title": "Junior Developer", "start_date": "2024-01", "end_date": None, "bullets": []},
    ],
    "education": [{"institution": "PUCMM", "degree": "BSc", "field": "Computer Science"}],
    "skills": [{"name": "Python"}, "FastAPI"],
    "screening_answers": [
        {"question": "¿Tienes autorización para trabajar en el país de la vacante?", "answer": "No"},
        {"question": "¿Requieres patrocinio de visa ahora o en el futuro?", "answer": "Sí, lo necesito"},
        {"question": "¿Cuál es tu expectativa salarial?", "answer": "USD 30,000 al año"},
    ],
}
USER = {"full_name": "Ana Prueba Pérez", "email": "ana@example.com"}


@pytest.fixture
def facts():
    return build_facts(USER, PROFILE)


def _field(drafted, key):
    return next(f for f in drafted.fields if f.key == key)


# ---------------------------------------------------------------- greenhouse


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://job-boards.greenhouse.io/canonical/jobs/6448444", ("canonical", "6448444")),
        ("https://boards.greenhouse.io/anthropic/jobs/123?gh_src=x", ("anthropic", "123")),
        ("https://job-boards.eu.greenhouse.io/amplemarket/jobs/4066973101", ("amplemarket", "4066973101")),
        ("https://boards.greenhouse.io/embed/job_app?for=acme&token=55", ("acme", "55")),
        ("greenhouse:stripe:999", ("stripe", "999")),
        ("https://jobs.lever.co/acme/abc", None),
        ("https://acme.com/careers?gh_jid=123", None),
        ("https://evilgreenhouse.io/acme/jobs/1", None),
        (None, None),
    ],
)
def test_parse_greenhouse_ref(value, expected):
    assert parse_greenhouse_ref(value) == expected


def test_parse_form_keeps_file_as_main_field_and_marks_sections():
    data = _form_data(
        compliance=[
            {
                "type": "eeoc",
                "questions": [_q("VeteranStatus", "veteran_status", "multi_value_single_select", False, [("No", "1")])],
            }
        ],
        demographic_questions={
            "questions": [
                {"id": 7, "label": "Pronouns", "required": False, "type": "multi_value_multi_select",
                 "answer_options": [{"id": 1, "label": "she/her"}]}
            ]
        },
        location_questions=[_q("Location (City)", "location")],
        include_ai_disclaimer=True,
        ai_disclaimer="&lt;p&gt;We use AI to review applications.&lt;/p&gt;",
        education="education_required",
    )
    form = parse_form(data, "acme", "123")
    resume = next(f for f in form.fields if f.key == "resume")
    assert resume.type == "file" and resume.alternatives == ["resume_text"]
    assert next(f for f in form.fields if f.key == "veteran_status").section == "compliance"
    demo = next(f for f in form.fields if f.key == "demographic_7")
    assert demo.section == "demographic" and demo.type == "multiselect" and demo.options[0]["label"] == "she/her"
    assert next(f for f in form.fields if f.key == "location").section == "location"
    assert form.notices == ["We use AI to review applications."]
    assert form.education_required is True


def test_form_url_points_at_greenhouse_even_for_company_career_pages():
    """Coinbase publica en su web con el formulario en un iframe, y la URL de
    Greenhouse redirige alli: el llenador tiene que ir a la de incrustar."""
    propia = parse_form(_form_data(absolute_url="https://www.coinbase.com/careers/positions/8?gh_jid=8"), "coinbase", "8")
    assert propia.url.startswith("https://www.coinbase.com/")
    assert propia.form_url == "https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=8"

    alojada = parse_form(_form_data(), "acme", "123")
    assert alojada.form_url == alojada.url == "https://job-boards.greenhouse.io/acme/jobs/123"


def test_hidden_fields_are_not_shown():
    data = _form_data({"label": "Source", "required": False, "fields": [{"name": "src", "type": "input_hidden"}]})
    assert all(f.key != "src" for f in parse_form(data, "acme", "1").fields)


# ---------------------------------------------------------------- classify


@pytest.mark.parametrize(
    "label,tipo,kind",
    [
        ("Please confirm that you have read and agree to Canonical's Recruitment Privacy Notice", "select", KIND_CONSENT),
        ("Agreement to Arbitrate", "select", KIND_CONSENT),
        ("Which gender do you identify as?", "select", KIND_SENSITIVE),
        ("Please indicate your nationality:", "multiselect", KIND_SENSITIVE),
        ("Do you require visa sponsorship?", "select", KIND_WORK_AUTH),
        ("In which country do you currently work?", "select", KIND_WORK_AUTH),
        ("What are your salary expectations?", "text", KIND_SALARY),
        ("LinkedIn Profile ", "text", KIND_IDENTITY),
        ("Describe your customer-facing experience.", "textarea", KIND_OPEN),
        # Regresion: la etiqueta menciona visas, pero la pregunta es si viajas.
        (CANONICAL_TRAVEL, "select", KIND_CHOICE),
        # Regresion (banco, GitLab): menciona "current employer" pero no pide su
        # nombre (se llenaba con la empresa). Es un dato personal del usuario.
        (
            "Are you subject to any employment agreements and/or post-employment restrictions with your "
            "current employer?",
            "select",
            KIND_PERSONAL,
        ),
        # Regresion (banco, GitLab): una pregunta de pais siempre se revisa.
        ("Please choose the country in which you are located.", "select", KIND_WORK_AUTH),
        # Regresiones del banco con IA: el modelo contestaba "No" a todas estas.
        ("Have you previously been employed by Coinbase in any capacity?", "select", KIND_PERSONAL),
        ("Have you previously worked at or consulted for GitLab?", "select", KIND_PERSONAL),
        ("Have you applied to the Fellows program before?", "select", KIND_PERSONAL),
        (
            "Are you a current government official or were you a government official in the last five years?",
            "select",
            KIND_PERSONAL,
        ),
        ("To your knowledge, were you referred to this position by a senior leader?", "select", KIND_PERSONAL),
        # ...y esta la sacaba del usuario de GitHub.
        ("GitLab Username:", "text", KIND_PERSONAL),
        # ...y para esta redactaba un "I understand...".
        (
            "Please note that you will not be considered unless you complete the Constellation application form.",
            "textarea",
            KIND_CONSENT,
        ),
        ("Are you able to handle on-call rotations?", "select", KIND_CHOICE),
    ],
)
def test_classify(label, tipo, kind):
    assert classify(FormField(key="question_9", label=label, type=tipo, required=True)) == kind


def test_question_core_takes_the_last_question_of_a_long_label():
    assert question_core(CANONICAL_TRAVEL) == "Are you willing and able to commit to this?"
    assert question_core("Do you require visa sponsorship?") == "Do you require visa sponsorship?"


@pytest.mark.parametrize(
    "text,topic",
    [
        ("¿Tienes autorización para trabajar en el país de la vacante?", "work_auth"),
        ("¿Requieres patrocinio de visa ahora o en el futuro?", "sponsorship"),
        ("Will you now or in the future require employment visa sponsorship?", "sponsorship"),
        ("Are you legally authorized to work in the United States?", "work_auth"),
        ("¿Cuál es tu expectativa salarial?", "salary"),
        ("¿Cuál es tu disponibilidad para comenzar / periodo de preaviso?", "start_date"),
        ("¿Cuántos años de experiencia tienes en tu rol principal?", "years_experience"),
        ("¿Por qué te interesa esta empresa?", "motivation"),
        (CANONICAL_TRAVEL, None),
    ],
)
def test_topic_of(text, topic):
    assert topic_of(text) == topic


def test_ai_policy_detection():
    assert mentions_ai_policy(
        "During this application process I agree to use only my own words. I understand that plagiarism, "
        "the use of AI or other generated content will disqualify my application."
    )
    assert mentions_ai_policy("AI Policy for Application")
    assert not mentions_ai_policy("Describe your experience building AI products.")


# ---------------------------------------------------------------- facts


def test_build_facts(facts):
    assert (facts["first_name"], facts["last_name"]) == ("Ana", "Prueba Pérez")
    assert facts["current_company"] == "Now Co"
    assert facts["skills"] == ["Python", "FastAPI"]
    assert {s["topic"] for s in facts["screening"]} == {"work_auth", "sponsorship", "salary"}
    assert missing_for_agent(facts) == []


def test_missing_for_agent_names_what_is_missing():
    faltan = missing_for_agent(build_facts({"full_name": "Ana", "email": "a@b.c"}, {"contact_info": {}}))
    assert "teléfono" in faltan and "LinkedIn" in faltan
    assert "respuesta guardada sobre patrocinio de visa" in faltan


# ---------------------------------------------------------------- borrador sin IA


def test_identity_resume_and_saved_answers(facts):
    data = _form_data(
        _yes_no("Do you require visa sponsorship?", "question_2"),
        _yes_no("Are you legally authorized to work in the country where this job is located?", "question_3"),
        _q("In which country do you currently work?", "question_4", "multi_value_single_select", True,
           [("Colombia", "10"), ("Dominican Republic", "11")]),
    )
    d = build_deterministic(parse_form(data, "acme", "1"), facts)
    assert _field(d, "first_name").display == "Ana"
    assert _field(d, "last_name").display == "Prueba Pérez"
    assert _field(d, "question_1").display == "https://linkedin.com/in/ana"
    assert _field(d, "resume").value == "master_cv"
    # "Sí, lo necesito" guardado -> la opcion "Yes" del formulario.
    assert (_field(d, "question_2").value, _field(d, "question_2").source) == ("1", "screening")
    assert _field(d, "question_3").value == "0"
    assert _field(d, "question_4").display == "Dominican Republic"
    assert "work_auth" in d.review_reasons
    assert d.auto_eligible is False


def test_travel_question_is_not_answered_with_the_visa_answer(facts):
    """La regresion que motivo question_core: antes salia "Yes" desde la
    respuesta guardada sobre patrocinio de visa."""
    d = build_deterministic(parse_form(_form_data(_yes_no(CANONICAL_TRAVEL, "question_5")), "acme", "1"), facts)
    campo = _field(d, "question_5")
    assert campo.status == NEEDS_USER and campo.value is None


def test_consent_and_sensitive_are_never_answered(facts):
    data = _form_data(
        _q("Please confirm that you have read and agree to our Privacy Notice", "question_6",
           "multi_value_single_select", True, [("Acknowledge/Confirm", "1")]),
        _q("Which gender do you identify as?", "question_7", "multi_value_single_select", True,
           [("Female", "1"), ("Prefer not to say", "2")]),
        compliance=[{"type": "eeoc", "questions": [
            _q("Race", "race", "multi_value_single_select", False, [("Decline to self identify", "8")])
        ]}],
    )
    d = build_deterministic(parse_form(data, "acme", "1"), facts)
    assert _field(d, "question_6").status == NEEDS_USER
    assert _field(d, "question_7").status == NEEDS_USER
    # Voluntaria: en blanco, que es una respuesta valida.
    assert _field(d, "race").status == SKIPPED and _field(d, "race").value is None
    assert {"consent", "sensitive"} <= set(d.review_reasons)


async def test_ai_policy_blocks_the_llm_and_open_answers(facts, monkeypatch):
    def no_llm(*_args, **_kwargs):
        raise AssertionError("con politica de IA no se llama al modelo")

    monkeypatch.setattr(draft_mod, "_ask_llm", no_llm)
    data = _form_data(_q("Why Acme?", "question_8", "textarea"), ai_policy=True)
    form = parse_form(data, "acme", "1")

    d = await build_draft(form, facts)
    assert d.ai_policy is True
    assert _field(d, "question_8").status == NEEDS_USER
    assert "sin IA" in _field(d, "question_8").reason
    # Los datos del perfil si se llenan: no son contenido generado.
    assert _field(d, "first_name").status == FILLED
    assert d.review_reasons[0] == "ai_policy"


def test_clean_form_is_eligible_for_auto(facts):
    d = build_deterministic(parse_form(_form_data(), "acme", "1"), facts)
    assert d.review_reasons == []
    assert d.auto_eligible is True
    assert d.stats()["required_filled"] == d.stats()["required"]


# ---------------------------------------------------------------- borrador con IA


class _FakeClient:
    def __init__(self, answers):
        self.calls = []
        self.messages = self
        self._answers = answers

    def create(self, **kwargs):
        self.calls.append(kwargs)
        texto = "Aqui va:\n" + json.dumps({"answers": self._answers})
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=texto)])


async def test_llm_answers_are_validated(facts, monkeypatch):
    data = _form_data(
        _q("Which languages do you use?", "question_10", "multi_value_multi_select", True,
           [("Python", "a"), ("Go", "b")]),
        _q("Which cloud do you prefer?", "question_11", "multi_value_single_select", True,
           [("AWS", "1"), ("GCP", "2")]),
        _q("Describe a backend project you built.", "question_12", "textarea"),
        _q("What is your favourite editor?", "question_13"),
        _q("How many companies have you worked for?", "question_14", "multi_value_multi_select", True,
           [("1", "x"), ("2", "y")]),
    )
    fake = _FakeClient([
        {"key": "question_10", "status": "answered", "value": ["Python"]},
        # Etiqueta que no existe: no se acepta.
        {"key": "question_11", "status": "answered", "value": "Azure"},
        {"key": "question_12", "status": "answered", "value": "I built an API with FastAPI at Now Co."},
        {"key": "question_13", "status": "unknown"},
        # Una valida y una inventada: todas o ninguna.
        {"key": "question_14", "status": "answered", "value": ["1", "7"]},
    ])
    monkeypatch.setattr(anthropic_client, "get_anthropic_client", lambda *a, **k: fake)

    d = await build_draft(parse_form(data, "acme", "1"), facts)
    assert len(fake.calls) == 1
    enviado = json.loads(fake.calls[0]["messages"][0]["content"])
    # El modelo no recibe el correo ni el telefono: no los necesita.
    assert "email" not in enviado["candidate_facts"] and "phone" not in enviado["candidate_facts"]

    assert (_field(d, "question_10").value, _field(d, "question_10").source) == (["a"], "ai")
    assert _field(d, "question_11").status == NEEDS_USER
    assert _field(d, "question_12").status == FILLED
    assert _field(d, "question_13").status == NEEDS_USER
    assert _field(d, "question_14").status == NEEDS_USER
    assert "open_text" in d.review_reasons and d.used_ai is True


async def test_saved_answer_goes_to_the_llm_as_a_hint(facts, monkeypatch):
    data = _form_data(_q("What are your salary expectations?", "question_15", "multi_value_single_select", True,
                         [("< 40k", "1"), ("40k+", "2")]))
    fake = _FakeClient([{"key": "question_15", "status": "answered", "value": "< 40k"}])
    monkeypatch.setattr(anthropic_client, "get_anthropic_client", lambda *a, **k: fake)

    d = await build_draft(parse_form(data, "acme", "1"), facts)
    pregunta = json.loads(fake.calls[0]["messages"][0]["content"])["questions"][0]
    assert pregunta["hint"] == "USD 30,000 al año"
    assert _field(d, "question_15").display == "< 40k"
    assert "salary" in d.review_reasons


async def test_legal_status_and_salary_need_a_saved_answer(monkeypatch):
    """Sin respuesta guardada, ni el patrocinio ni el salario llegan al
    modelo: en el banco contestaba "No" a "¿necesitas patrocinio?". La zona
    horaria si, porque sale de la ubicacion del perfil."""
    sin_guardadas = build_facts(USER, {**PROFILE, "screening_answers": []})
    data = _form_data(
        _yes_no("Will you now or in the future require sponsorship for a visa?", "question_20"),
        _q("What are your salary expectations?", "question_21"),
        _q("What is the timezone you plan to work from?", "question_22"),
        _yes_no("Have you previously worked at or consulted for Acme?", "question_23"),
    )
    fake = _FakeClient([{"key": "question_22", "status": "answered", "value": "GMT-4"}])
    monkeypatch.setattr(anthropic_client, "get_anthropic_client", lambda *a, **k: fake)

    d = await build_draft(parse_form(data, "acme", "1"), sin_guardadas)
    preguntadas = [q["key"] for q in json.loads(fake.calls[0]["messages"][0]["content"])["questions"]]
    assert preguntadas == ["question_22"]
    assert _field(d, "question_20").status == NEEDS_USER
    assert "Guarda en tu perfil" in _field(d, "question_20").reason
    assert _field(d, "question_21").status == NEEDS_USER
    assert _field(d, "question_22").display == "GMT-4"
    assert _field(d, "question_23").kind == KIND_PERSONAL and _field(d, "question_23").status == NEEDS_USER
    assert "personal" in d.review_reasons


async def test_saved_text_answers_are_adapted_not_copied(facts, monkeypatch):
    """Las respuestas guardadas estan en espanol y el formulario en ingles: sin
    politica de IA, van al modelo como pista en vez de copiarse."""
    fake = _FakeClient([{"key": "question_30", "status": "unknown"}])
    monkeypatch.setattr(anthropic_client, "get_anthropic_client", lambda *a, **k: fake)
    data = _form_data(_q("What are your salary expectations?", "question_30"))

    d = await build_draft(parse_form(data, "acme", "1"), facts)
    pregunta = json.loads(fake.calls[0]["messages"][0]["content"])["questions"][0]
    assert pregunta["hint"] == "USD 30,000 al año"
    campo = _field(d, "question_30")
    assert campo.status == NEEDS_USER and campo.value is None
    assert "respuesta guardada" in campo.reason


async def test_with_ai_policy_saved_answers_go_verbatim(facts, monkeypatch):
    """Con politica contra IA no hay modelo: la respuesta guardada son
    palabras del propio usuario y se copia tal cual (y se revisa)."""
    monkeypatch.setattr(draft_mod, "_ask_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sin IA")))
    data = _form_data(_q("What are your salary expectations?", "question_31"), ai_policy=True)
    d = await build_draft(parse_form(data, "acme", "1"), facts)
    campo = _field(d, "question_31")
    assert (campo.value, campo.source) == ("USD 30,000 al año", "screening")
    assert {"ai_policy", "salary"} <= set(d.review_reasons)


def test_profile_country_does_not_answer_citizenship(facts):
    data = _form_data(
        _q("What country are you a citizen of?", "question_32", "multi_value_single_select", True,
           [("Dominican Republic", "1"), ("Spain", "2")])
    )
    campo = _field(build_deterministic(parse_form(data, "acme", "1"), facts), "question_32")
    assert campo.status == NEEDS_USER and campo.value is None


def test_filler_helpers_need_no_browser():
    """El llenador corre en su propio contenedor, pero sus reglas se prueban
    aqui: importarlo no carga Playwright."""
    from app.services.apply_agent import filler

    assert filler._element_id("question_52769063[]") == "question_52769063"
    assert filler._element_id("location") == "candidate-location"
    assert filler._element_id("first_name") == "first_name"

    identidad = {"key": "email", "kind": "identity", "type": "text", "value": "ana@example.com"}
    abierta = {"key": "question_2", "kind": "open_text", "type": "textarea", "value": "Texto real"}
    opcion = {"key": "question_3", "kind": "choice", "type": "select", "value": "1"}
    # En modo seguro no se teclea ningun dato del usuario en la pagina.
    assert filler._value_for(identidad, safe=True) == "prueba.jobpilot@example.com"
    assert filler._value_for(abierta, safe=True) == filler.SAFE_TEXT
    assert filler._value_for(opcion, safe=True) == "1"
    assert filler._value_for(identidad, safe=False) == "ana@example.com"

    # La red de seguridad: un POST de envio se aborta.
    assert filler._SUBMIT_POST.search("https://boards-api.greenhouse.io/v1/boards/acme/jobs/1/applications")
    assert filler._SUBMIT_POST.search("https://job-boards.greenhouse.io/acme/jobs/1/application")
    assert not filler._SUBMIT_POST.search("https://www.recaptcha.net/recaptcha/enterprise/anchor")


async def test_without_ai_pending_fields_go_to_the_user(facts, monkeypatch):
    monkeypatch.setattr(anthropic_client, "get_anthropic_client", lambda *a, **k: None)
    data = _form_data(_q("Describe a backend project you built.", "question_12", "textarea"))
    d = await build_draft(parse_form(data, "acme", "1"), facts)
    assert _field(d, "question_12").status == NEEDS_USER
    assert d.used_ai is False and "needs_user" in d.review_reasons
