# Cómo contribuir

`main` es **producción**: lo que está en `main` es lo que corre. Nadie empuja a `main`
directo; todo entra por Pull Request con el CI en verde.

## Flujo

1. Haz un fork (o, si tienes acceso, una rama): `git checkout -b feat/lo-que-sea`.
2. Levanta tu entorno local (abajo) y trabaja ahí.
3. Abre un PR contra `main`. El CI corre tests del backend, deriva de esquema, lint y
   build del frontend. Si falla, no se mezcla.
4. El mantenedor revisa y mezcla. Solo entonces llega a producción.

Desplegar (solo el mantenedor, en la PC de producción): siempre desde `main`.

```bash
git checkout main && git pull && docker compose up -d --build
```

## Entorno local

```bash
cp .env.example .env   # rellena POSTGRES_PASSWORD y JWT_SECRET (el archivo dice cómo generarlos)
docker compose up --build
```

Frontend en http://localhost:3000, backend en http://localhost:8000. Tu base es tuya y
empieza vacía; no hay forma de tocar la de producción desde tu máquina.

### Si ya corres producción en la misma PC

Levanta desarrollo al lado, con otros puertos (3002/8001/5433) y su propia base:

```bash
docker compose -p jobpilot-dev --env-file .env --env-file dev.env up -d --build
```

Bórralo entero (base incluida) con `docker compose -p jobpilot-dev down -v`. Sin el `-p`,
el comando apunta a producción.
