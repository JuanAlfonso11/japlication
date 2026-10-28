"""Avisos al telefono sobre una aplicacion en curso.

Mismo patron que el aviso de vacantes nuevas (routers/jobs.py): sin Firebase
configurado no hace nada, y un token muerto se borra en vez de fallar igual
en cada aviso. El `data` lleva el id de la postulacion para que tocar el aviso
abra su revision.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_token import DeviceToken
from app.services import push_notifications

logger = logging.getLogger("jobflow.apply")


async def notify(db: AsyncSession, user_id: UUID, title: str, body: str, application_id: UUID) -> None:
    if not push_notifications.is_configured():
        return
    from firebase_admin import messaging

    tokens = (await db.execute(select(DeviceToken.token).where(DeviceToken.user_id == user_id))).scalars().all()
    muertos: list[str] = []
    data = {"type": "apply_draft", "application_id": str(application_id)}
    for token in tokens:
        try:
            await asyncio.to_thread(push_notifications.send_push, token, title, body, data)
        except messaging.UnregisteredError:
            muertos.append(token)
        except Exception:  # noqa: BLE001 - un aviso nunca tumba el envio
            logger.exception("No se pudo avisar de la aplicacion %s", application_id)
    if muertos:
        await db.execute(delete(DeviceToken).where(DeviceToken.token.in_(muertos)))
        await db.commit()
