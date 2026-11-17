#!/bin/sh
# Equipo IA V3.1: repositorio SOLO LOCAL por decisión del usuario. Ningún «git push» está permitido.
# Instalación (desde la carpeta que contiene equipo_ia_v3/): copiar este archivo a .git/hooks/pre-push
echo "Equipo IA: este repositorio es solo local; push bloqueado (ver equipo_ia_v3/docs/V31_GIT_LOCAL.md)." >&2
exit 1
