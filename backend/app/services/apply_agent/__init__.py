"""Agente de aplicacion: prepara la candidatura a una vacante a partir del perfil.

Plan completo (fases, puertas, modos de envio y la parte legal) en
tasks/agente-aplicacion.md. Esta fase solo arma BORRADORES: nada de aqui envia
una candidatura.

Piezas:
  * greenhouse.py -- lee el formulario por la API publica de Greenhouse.
  * classify.py   -- decide que clase de campo es cada pregunta.
  * facts.py      -- el perfil del usuario como hechos que se pueden citar.
  * draft.py      -- llena lo que se puede, deja lo demas al usuario, y dice
                     si el borrador seria apto para el modo automatico.
"""
