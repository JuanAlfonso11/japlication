"""Postular por correo. Lo que importa es lo que NO pasa.

Esto manda un correo con el nombre del usuario a un empleador real, y un correo
enviado no se retira. Así que casi todos estos tests comprueban un camino en el
que NO se envía nada: sin configurar, huella distinta, ya postulada, sin CV,
destinatario rechazado.

Ningún test envía un correo de verdad: todos van contra un SMTP falso que
registra lo que recibe. Sin eso, correr la suite postularía a empresas reales.
"""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.career_profile import CareerProfile
from app.models.cover_letter import CoverLetter
from app.models.enums import ApplicationStatus, GenerationSource, JobSource
from app.models.job import Job
from app.models.resume_version import ResumeVersion
from app.services import apply_by_email
from app.services.apply_by_email import (
    ApplyEmailError,
    Attachment,
    EmailApplication,
    build_email_application,
    send_email_application,
)

CV_CONTENT = {
    "summary": "Ingeniero backend con ocho años construyendo servicios en Python.",
    "skills": ["Python", "PostgreSQL", "Docker"],
    "experience": [
        {"company": "Acme", "title": "Ingeniero backend", "start_date": "2020-01",
         "end_date": None, "achievements": ["Migró el pipeline de ingesta a colas."]}
    ],
    "education": [{"institution": "Universidad", "degree": "Ingeniería", "field": "Informática"}],
}


class FakeSMTP:
    """Registra en vez de enviar. `rechazar` simula un destinatario que el
    servidor no acepta sin lanzar excepción, que es lo que hace smtplib."""

    enviados: list = []
    rechazar = False

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, message):
        FakeSMTP.enviados.append(message)
        return {message["To"]: (550, b"no such user")} if FakeSMTP.rechazar else {}


@pytest.fixture
def smtp_falso(monkeypatch):
    FakeSMTP.enviados = []
    FakeSMTP.rechazar = False
    monkeypatch.setattr(apply_by_email.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(settings, "SMTP_USER", "juan.personal@example.test")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "no-es-real")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", True)
    return FakeSMTP


def _app(**over):
    base = dict(
        to="talento@acme.test",
        reply_to="juan@example.test",
        full_name="Juan Alfonso",
        job_title="Ingeniero backend",
        company="Acme",
        cover_letter_text="Estimado equipo de Acme: me interesa mucho esta posición.",
        resume_pdf=b"%PDF-cv",
        cover_letter_pdf=b"%PDF-carta",
    )
    base.update(over)
    return build_email_application(**base)


# --- construir el correo ----------------------------------------------------

def test_la_carta_es_el_cuerpo_y_los_pdfs_van_adjuntos():
    app = _app()

    assert app.subject == "Candidatura: Ingeniero backend — Juan Alfonso"
    assert "me interesa mucho" in app.body
    assert [a.filename for a in app.attachments] == ["CV_Juan_Alfonso.pdf", "Carta_Juan_Alfonso.pdf"]


def test_sin_carta_hay_un_cuerpo_minimo_y_solo_el_cv():
    app = _app(cover_letter_text=None, cover_letter_pdf=None)

    assert "Adjunto mi CV" in app.body
    assert [a.filename for a in app.attachments] == ["CV_Juan_Alfonso.pdf"]


def test_la_huella_cambia_si_cambia_un_adjunto_con_el_mismo_nombre():
    # Un CV regenerado se llama igual y dice otra cosa. Si la huella solo
    # mirara el nombre, se enviaría algo que el usuario no ha visto.
    a = _app(resume_pdf=b"%PDF-version-1")
    b = _app(resume_pdf=b"%PDF-version-2")

    assert a.attachments[0].filename == b.attachments[0].filename
    assert a.fingerprint() != b.fingerprint()


def test_la_huella_es_estable_para_el_mismo_contenido():
    assert _app().fingerprint() == _app().fingerprint()


# --- enviar -----------------------------------------------------------------

def test_sin_smtp_es_un_error_no_un_silencio(monkeypatch):
    # El test que más importa. email._send, sin SMTP, registra en el log y
    # vuelve como si nada: el usuario creería haber postulado y la candidatura
    # no habría salido nunca.
    monkeypatch.setattr(settings, "SMTP_HOST", "")

    with pytest.raises(ApplyEmailError):
        send_email_application(_app())


def test_sale_de_la_cuenta_del_usuario_y_responde_a_su_correo(smtp_falso):
    send_email_application(_app())

    assert len(smtp_falso.enviados) == 1
    msg = smtp_falso.enviados[0]
    # De la cuenta autenticada, no de SMTP_FROM_EMAIL, que es un no-reply.
    assert msg["From"] == "juan.personal@example.test"
    assert msg["Reply-To"] == "juan@example.test"
    assert msg["To"] == "talento@acme.test"
    adjuntos = [p.get_filename() for p in msg.iter_attachments()]
    assert adjuntos == ["CV_Juan_Alfonso.pdf", "Carta_Juan_Alfonso.pdf"]


def test_un_destinatario_rechazado_no_cuenta_como_enviado(smtp_falso):
    # smtplib devuelve los rechazados en vez de lanzar; ignorarlo sería marcar
    # como postulada una candidatura que no llegó.
    smtp_falso.rechazar = True

    with pytest.raises(ApplyEmailError):
        send_email_application(_app())


# --- el endpoint: los caminos en que no se envía ------------------------------

async def _setup(user, *, apply_email="talento@acme.test", con_cv=True, con_carta=True):
    async with AsyncSessionLocal() as db:
        profile = CareerProfile(user_id=user.id, contact_info={"city": "Santo Domingo"})
        db.add(profile)
        job = Job(
            imported_by=user.id,
            source=JobSource.url_import,
            source_url="https://acme.test/careers/backend",
            title="Ingeniero backend",
            company="Acme",
            location="Remoto",
            description="Envía tu CV a talento@acme.test",
            requirements=[],
            responsibilities=[],
            skills_required=[],
            apply_email=apply_email,
        )
        db.add(job)
        await db.flush()
        if con_cv:
            db.add(ResumeVersion(
                user_id=user.id, career_profile_id=profile.id, job_id=job.id,
                title="CV Acme", content=CV_CONTENT, change_log=[], language="es",
                generated_by=GenerationSource.manual,
            ))
        if con_carta:
            db.add(CoverLetter(
                user_id=user.id, job_id=job.id,
                content="Estimado equipo de Acme: me interesa mucho esta posición.",
                generated_by=GenerationSource.manual,
            ))
        await db.commit()
        return job.id


async def test_vista_previa_sin_correo_publicado_dice_por_que(async_client, user_and_headers, smtp_falso):
    user, headers = user_and_headers
    job_id = await _setup(user, apply_email=None)

    r = await async_client.get(f"/jobs/{job_id}/apply-email", headers=headers)

    assert r.status_code == 200
    assert any("no publica un correo" in b for b in r.json()["blockers"])


async def test_sin_cv_adaptado_no_se_puede_enviar(async_client, user_and_headers, smtp_falso):
    user, headers = user_and_headers
    job_id = await _setup(user, con_cv=False)

    r = await async_client.get(f"/jobs/{job_id}/apply-email", headers=headers)

    assert any("CV adaptado" in b for b in r.json()["blockers"])


async def test_una_huella_distinta_no_envia_nada(async_client, user_and_headers, smtp_falso):
    user, headers = user_and_headers
    job_id = await _setup(user)

    r = await async_client.post(
        f"/jobs/{job_id}/apply-email", json={"fingerprint": "no-es-la-de-la-vista-previa"}, headers=headers
    )

    assert r.status_code == 409
    assert smtp_falso.enviados == []


async def test_el_camino_feliz_envia_una_vez_y_marca_postulada(async_client, user_and_headers, smtp_falso):
    user, headers = user_and_headers
    job_id = await _setup(user)

    preview = (await async_client.get(f"/jobs/{job_id}/apply-email", headers=headers)).json()
    assert preview["blockers"] == [], preview["blockers"]
    assert preview["to"] == "talento@acme.test"

    r = await async_client.post(
        f"/jobs/{job_id}/apply-email", json={"fingerprint": preview["fingerprint"]}, headers=headers
    )

    assert r.status_code == 200, r.text
    assert len(smtp_falso.enviados) == 1
    async with AsyncSessionLocal() as db:
        fila = (await db.execute(select(Application).where(Application.job_id == job_id))).scalar_one()
    assert fila.status == ApplicationStatus.applied
    assert fila.applied_at is not None
    assert "talento@acme.test" in (fila.notes or "")


async def test_no_se_postula_dos_veces(async_client, user_and_headers, smtp_falso):
    # Dos correos iguales al mismo reclutador restan, no suman.
    user, headers = user_and_headers
    job_id = await _setup(user)
    preview = (await async_client.get(f"/jobs/{job_id}/apply-email", headers=headers)).json()
    await async_client.post(
        f"/jobs/{job_id}/apply-email", json={"fingerprint": preview["fingerprint"]}, headers=headers
    )

    segundo = await async_client.post(
        f"/jobs/{job_id}/apply-email", json={"fingerprint": preview["fingerprint"]}, headers=headers
    )

    assert segundo.status_code == 409
    assert len(smtp_falso.enviados) == 1


def test_dos_renders_del_mismo_contenido_dan_la_misma_huella():
    # La regresión del bug que cazó el camino feliz: reportlab mete fecha y un
    # /ID aleatorio en cada PDF, así que los BYTES cambian aunque el CV sea el
    # mismo. La huella tiene que medir el origen.
    a = _app(resume_pdf=b"%PDF-render-1", resume_source=b"mismo-cv")
    b = _app(resume_pdf=b"%PDF-render-2", resume_source=b"mismo-cv")

    assert a.fingerprint() == b.fingerprint()


def test_si_cambia_el_origen_cambia_la_huella():
    a = _app(resume_source=b"cv-version-1")
    b = _app(resume_source=b"cv-version-2")

    assert a.fingerprint() != b.fingerprint()
