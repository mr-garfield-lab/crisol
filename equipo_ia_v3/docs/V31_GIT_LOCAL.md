# V3.1 · Git exclusivamente local

**Estado:** preparado el 2026-11-11 (etapa de mantenimiento). Git para Windows 2.56.0.4, instalado con autorización
del usuario mediante `winget` (paquete oficial `Git.Git`, instalador verificado por SHA-256).

## Dónde y cómo

- **Repositorio:** la carpeta que contiene `equipo_ia_v3/`, `fuentes/` y `AGENTS.md` (la misma que empaqueta
  `v3/empaquetar.py`). El historial de las Etapas 0–8 de V3 no venía en el ZIP original; este repositorio empieza en
  el estado verificado del cierre de F0.5.
- **Ramas:** `main` = estado verificado del cierre de F0.5 (primer commit). El trabajo va en ramas propias (la del
  mantenimiento es `mantenimiento-v31`), como pide `AGENTS.md`; no se fusiona con `main` sin el usuario.
- **Sin remotos:** `git remote` está vacío y `push.default = nothing`.
- **Guardia contra publicar:** `.git/hooks/pre-push` rechaza cualquier `push` (copia versionada en
  `v3/git_pre_push_solo_local.sh`). Comprobado: un `push` a un repositorio local de prueba se rechaza y no llega nada.
- **Bytes exactos:** `.gitattributes` con `* -text` y `core.autocrlf = false` en el repositorio (Git para Windows
  activa `autocrlf = true` para todo el sistema). Comprobado: un clon reproduce los 736 archivos con el mismo SHA-256,
  así que `sistema/MANIFIESTO_SHA256.txt` sigue coincidiendo.
- **Exclusiones** (`.gitignore`): las mismas que el empaquetado (cachés, bases SQLite, modelos GGUF, ZIP, `dist/`).
- **Identidad:** local y genérica (`Equipo IA (local)`, sin correo real). Ningún dato personal en el historial.
- **Originales:** `originales/` (ZIP y plan recibidos, con su `SHA256SUMS.txt`) está FUERA del repositorio y no se
  toca.

## Uso habitual

```powershell
git status
git log --oneline
git diff main..mantenimiento-v31 --stat
```

No hay `git push`, `git remote add` ni publicaciones: si algún día se quisiera, sería una decisión explícita del
usuario, retirando antes la guardia.
