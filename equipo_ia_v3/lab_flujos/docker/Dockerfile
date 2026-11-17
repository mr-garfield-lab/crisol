# Equipo IA V3.1 — banco de flujos grandes: imagen de VERIFICACIÓN (CPU, sin GPU, sin modelos, sin red).
#
# Desde la carpeta raíz del paquete (la que contiene equipo_ia_v3/ y fuentes/):
#     docker build -f equipo_ia_v3/lab_flujos/docker/Dockerfile -t equipo-ia-flujos .
#     docker run --rm --network none equipo-ia-flujos
#
# Qué comprueba (unos minutos de CPU): las pruebas propias de Contexto Ligero V3.5 y las 10 comprobaciones del banco
# de flujos con cerebros FALSOS (reproducibilidad frente al PC de origen, parar y reanudar sin perder trabajo,
# verificación estricta, trampas y flujo de identidad). NO ejecuta cerebros reales: eso se hace en Windows con una
# GPU NVIDIA, siguiendo equipo_ia_v3/GUIA_AMIGO_BANCOS.md.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONUNBUFFERED=1
RUN useradd --no-create-home --shell /usr/sbin/nologin equipo
WORKDIR /opt/equipo
COPY --chown=equipo:equipo . .
USER equipo
WORKDIR /opt/equipo/equipo_ia_v3
CMD ["sh", "lab_flujos/docker/verificar.sh"]
