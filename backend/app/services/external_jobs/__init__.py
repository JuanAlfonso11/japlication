"""Registro de los proveedores de busqueda de empleo externos.

Ver registry.py. El paquete existia vacio (solo __pycache__ de un intento
anterior que se revirtio); esta es la version que si se usa.
"""

from app.services.external_jobs.registry import (
    PROVIDER_NAMES,
    PROVIDER_NAMES_PATTERN,
    PROVIDERS,
    ProviderSpec,
    SearchParams,
    get_provider,
)

__all__ = [
    "PROVIDERS",
    "PROVIDER_NAMES",
    "PROVIDER_NAMES_PATTERN",
    "ProviderSpec",
    "SearchParams",
    "get_provider",
]
