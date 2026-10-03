# JobPilot Autofill (extensión de Chrome)

Rellena el formulario de postulación abierto con tus datos de contacto y tu banco de
respuestas de JobPilot. **Nunca envía**: revisas y pulsas "Submit" tú.

## Instalar
1. `chrome://extensions` → activa *Modo de desarrollador*.
2. *Cargar descomprimida* → elige esta carpeta `extension/`.

## Usar
1. Abre una vacante en JobPilot: el *Kit de aplicación* sincroniza tus datos con la extensión.
2. Abre el formulario de la empresa → icono de JobPilot → **Rellenar esta página**.
3. Los campos rellenados quedan en verde; los que faltan se listan en el popup.
   Añádelos en el Kit ("+ Añadir una pregunta…") y la próxima vez se rellenan solos.

No sube el CV (adjúntalo a mano). Los formularios dentro de un iframe de otro dominio solo se
rellenan si ese dominio está en `host_permissions` del manifest (los ATS comunes ya lo están).
Si usas JobPilot en otra dirección, añádela en `content_scripts.matches`.

Prueba de la lógica de coincidencia: `node extension/fill.test.js`.
