# Banco local para evaluar modelos de IA: Blender (filtro + Blender sin ventana + verificador) y diagnóstico de
# partidas de Project Zomboid / RimWorld (traductor + generador de daños). Ver LEEME.md.
# Construir:  docker build -t banco-local-ia .
# La imagen descarga Blender de blender.org (unos 400 MB). No incluye ningún modelo de IA ni ninguna partida.
FROM python:3.12-slim

ARG BLENDER_URL=https://download.blender.org/release/Blender5.2/blender-5.2.3-linux-x64.tar.xz

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils \
        libx11-6 libxrender1 libxxf86vm1 libxfixes3 libxi6 libxkbcommon0 libsm6 libice6 libgl1 libegl1 libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/blender \
    && curl -fsSL "$BLENDER_URL" -o /tmp/blender.tar.xz \
    && tar -xJf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 \
    && rm /tmp/blender.tar.xz \
    && /opt/blender/blender --version

ENV BLENDER_EXE=/opt/blender/blender \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1

# usuario sin privilegios: los scripts que escriben los modelos se ejecutan dentro de Blender con este usuario; el
# diagnóstico de partidas solo lee los archivos que montes (de preferencia en modo :ro)
RUN useradd --create-home --uid 10001 banco && mkdir -p /datos && chown banco:banco /datos
WORKDIR /app
COPY --chown=banco:banco lab_blender/ /app/lab_blender/
COPY --chown=banco:banco lab_saves/ /app/lab_saves/
COPY --chown=banco:banco pruebas/ /app/pruebas/
COPY --chown=banco:banco LEEME.md MANIFIESTO.json /app/
USER banco
VOLUME ["/datos"]

# sin argumentos: muestra la ayuda del banco de Blender. El otro banco: lab_saves/portable.py --help. Ver LEEME.md.
ENTRYPOINT ["python", "-B", "-X", "utf8"]
CMD ["lab_blender/portable.py", "--help"]
