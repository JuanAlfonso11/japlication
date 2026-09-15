"""Blocks the job importer from being pointed at internal infrastructure.

`POST /jobs/import` takes a URL from the user and the backend fetches it.
Until this existed the URL was an unvalidated `str` handed straight to
`httpx.get(..., follow_redirects=True)`, which meant any authenticated user
could make the backend issue arbitrary GETs from *inside* the Docker
network and read the response back as a "job description" — that's a
server-side request forgery, and the reachable targets here are real:

  * `http://db:5432` and the backend's own `http://backend:8000`
  * the Docker host, and through it whatever the machine exposes on
    localhost (the APK server, the offline page, `tailscale` endpoints)
  * `http://169.254.169.254/` style link-local metadata addresses

The share-target feature makes it worse in practice, not better: sharing
into JobPilot is now the easiest possible way to feed the importer a URL.

Two things are enforced:

1. **Scheme.** Only http/https. Rules out `file://`, `gopher://` and the
   rest of the classic SSRF scheme tricks.
2. **Destination.** The hostname is resolved and every address it maps to
   must be a public unicast one. Private, loopback, link-local, multicast
   and reserved ranges are refused — checking every resolved address, not
   just the first, so a host with one public and one internal A record
   can't sneak through.

Redirects are deliberately NOT delegated to httpx: `follow_redirects=True`
would validate only the URL the user typed and then happily follow a 302 to
`http://localhost`. The caller follows them one hop at a time and
re-validates each.

Residual risk, stated plainly: this validates the name at check time, so a
DNS entry that returns a public address on the first lookup and a private
one microseconds later (DNS rebinding) is not covered. Closing that needs
pinning the connection to the validated IP, which httpx doesn't express
cleanly without giving up SNI/Host correctness. For a single-tenant app
behind Tailscale that trade is the right one, and it's a much smaller hole
than the one this closes.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")


class UnsafeUrlError(ValueError):
    """The URL is malformed, uses a disallowed scheme, or resolves to an
    address the backend must not be tricked into contacting."""


def _is_public_address(raw: str) -> bool:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False

    # IPv6-mapped IPv4 (::ffff:127.0.0.1) must be judged on the IPv4 address
    # it actually reaches, or loopback slips through as "a v6 address".
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped

    # `is_global` en vez de la lista de negaciones que habia aqui. La lista
    # parecia equivalente y no lo era: 100.64.0.0/10 -- el rango CGNAT, que es
    # justo el que usa Tailscale -- no es private, ni loopback, ni link-local,
    # ni reserved, asi que pasaba entero. Comprobado: 100.64.1.1 daba
    # _is_public=True con la version anterior. Por ahi se alcanzaba cualquier
    # nodo de la tailnet y el servidor de APK del propio equipo en :8446, que
    # es precisamente lo que este modulo dice en su cabecera que bloquea.
    #
    # CPython excluye ese rango solo dentro de `is_global`, nunca lo mete en
    # `_private_networks`, asi que no era cuestion de version de Python.
    return address.is_global


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"No se pudo resolver el dominio: {host}") from exc
    return [info[4][0] for info in infos]


def validate_public_http_url(url: str) -> str:
    """Returns the URL unchanged if it is safe to fetch, else raises
    `UnsafeUrlError`."""
    if not url or not url.strip():
        raise UnsafeUrlError("La URL está vacía.")

    candidate = url.strip()

    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise UnsafeUrlError("La URL no es válida.") from exc

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("Solo se admiten enlaces http y https.")

    host = parts.hostname
    if not host:
        raise UnsafeUrlError("La URL no tiene un dominio válido.")

    # A literal IP needs no DNS round trip, and going through getaddrinfo
    # for one would let a "hostname" that is really an IP be judged twice.
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = _resolve(host)

    if not addresses:
        raise UnsafeUrlError(f"No se pudo resolver el dominio: {host}")

    for address in addresses:
        if not _is_public_address(address):
            raise UnsafeUrlError(
                "Ese enlace apunta a una dirección interna y no se puede importar."
            )

    return candidate
