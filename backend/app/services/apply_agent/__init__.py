"""Agente de aplicacion: prepara y envia la candidatura a una vacante a partir
del perfil, cuando el usuario desliza a la derecha ("aplicar al deslizar").

Plan completo (fases, puertas, modos de envio y la parte legal) en
tasks/agente-aplicacion.md.

Piezas:
  * greenhouse.py   -- lee el formulario por la API publica de Greenhouse.
  * classify.py     -- decide que clase de campo es cada pregunta.
  * facts.py        -- el perfil del usuario como hechos que se pueden citar.
  * draft.py        -- llena lo que se puede, deja lo demas al usuario, y dice
                       si el borrador seria apto para el modo automatico.
  * gates.py        -- requisitos que descartan una oferta (permiso, idioma...).
  * grounding.py    -- auditoria de hechos del CV y la carta contra el perfil.
  * review.py       -- respuestas del usuario y que falta para poder enviar.
  * pipeline.py     -- lo que pasa tras el swipe: todo lo anterior junto.
  * submit.py       -- el envio (correo, Greenhouse por el agente, o a mano) y
                       el reloj de los envios programados.
  * filler.py / agent_server.py -- el navegador, en su propio contenedor.

Nada de aqui responde un consentimiento, inventa un hecho o toca un CAPTCHA.
"""
