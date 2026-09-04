import asyncio

from app.services import francetravail

SAMPLE_OFFER = {
    "id": "ABC123",
    "intitule": "Ingénieur Backend Senior",
    "entreprise": {"nom": "Acme Corp"},
    "description": "Nous recherchons un ingénieur backend avec de l'expérience en Python et Docker.",
    "lieuTravail": {"libelle": "Paris (75)"},
    "typeContrat": "CDI",
    "dateCreation": "2026-09-01T12:00:00.000Z",
    "salaire": {"libelle": "Annuel de 45000.0 Euros à 55000.0 Euros"},
    "origineOffre": {"urlOrigine": "https://candidat.francetravail.fr/offres/recherche/detail/ABC123"},
}


def test_is_configured_requires_both_settings(monkeypatch):
    monkeypatch.setattr(francetravail.settings, "FRANCE_TRAVAIL_CLIENT_ID", None)
    monkeypatch.setattr(francetravail.settings, "FRANCE_TRAVAIL_CLIENT_SECRET", None)
    assert francetravail.is_configured() is False
    monkeypatch.setattr(francetravail.settings, "FRANCE_TRAVAIL_CLIENT_ID", "id")
    monkeypatch.setattr(francetravail.settings, "FRANCE_TRAVAIL_CLIENT_SECRET", "secret")
    assert francetravail.is_configured() is True


def test_normalize_maps_fields():
    normalized = francetravail._normalize(SAMPLE_OFFER)
    assert normalized["title"] == "Ingénieur Backend Senior"
    assert normalized["company"] == "Acme Corp"
    assert normalized["francetravail_job_id"] == "ABC123"
    assert normalized["source"] == "francetravail"
    assert normalized["employment_type"] == "full_time"
    assert normalized["salary_min"] == 45000.0
    assert normalized["salary_max"] == 55000.0
    assert normalized["salary_currency"] == "EUR"


def test_search_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(francetravail.settings, "FRANCE_TRAVAIL_CLIENT_ID", None)
    monkeypatch.setattr(francetravail.settings, "FRANCE_TRAVAIL_CLIENT_SECRET", None)
    try:
        asyncio.run(francetravail.search_francetravail_jobs(q="backend"))
        assert False, "expected FranceTravailError"
    except francetravail.FranceTravailError:
        pass


def test_search_fetches_token_then_offers(monkeypatch):
    monkeypatch.setattr(francetravail.settings, "FRANCE_TRAVAIL_CLIENT_ID", "id")
    monkeypatch.setattr(francetravail.settings, "FRANCE_TRAVAIL_CLIENT_SECRET", "secret")

    class FakeTokenResponse:
        status_code = 200

        def json(self):
            return {"access_token": "fake-token", "expires_in": 1499}

    class FakeSearchResponse:
        status_code = 200
        headers = {"Content-Range": "offres 0-0/1"}

        def json(self):
            return {"resultats": [SAMPLE_OFFER]}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data=None, headers=None):
            return FakeTokenResponse()

        async def get(self, url, params=None, headers=None):
            return FakeSearchResponse()

    monkeypatch.setattr(francetravail.httpx, "AsyncClient", FakeAsyncClient)
    francetravail._search_cache.clear()
    francetravail._token_cache.clear()

    data = asyncio.run(francetravail.search_francetravail_jobs(q="backend"))
    assert len(data["results"]) == 1
    assert francetravail.get_cached_result("ABC123") is not None
    assert francetravail._token_cache["token"] == "fake-token"

    data = asyncio.run(francetravail.search_francetravail_jobs(q="backend", experience_level_filter="entry"))
    assert data["results"] == []
