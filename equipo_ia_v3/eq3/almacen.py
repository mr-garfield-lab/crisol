"""Equipo IA V3 · ALMACÉN SQLite de SOLO AÑADIR con cadena de hashes (base común de la traza y de los cambios).

Una subclase declara ESQUEMA (CREATE TABLE...), TABLAS ({tabla: columnas}), CLAVES ({tabla: columnas clave},
por defecto ("id",)) y ESQUEMA_VERSION. El almacén garantiza:

- **Solo se añade:** hay disparadores BEFORE UPDATE y BEFORE DELETE en todas las tablas, incluidas `meta` y
  `registro`.
- **Cadena de hashes:** cada fila insertada se copia en `registro`, con hash = sha256(hash_previo + tabla +
  clave + JSON canónico). `verificar_cadena()` recalcula la cadena y exige que cada tabla contenga EXACTAMENTE
  lo registrado; así detecta las alteraciones aunque alguien quite los disparadores.
- **Integridad:** las claves foráneas están activas. La inserción y las consultas solo aceptan tablas y columnas
  de las listas blancas declaradas, y todos los valores van parametrizados.
- **Transacciones de todo o nada:** un error o un STOP no dejan filas parciales.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


class ErrorAlmacen(Exception):
    """Esquema incompatible, inserción o consulta inválida."""


def ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonico(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class Almacen:
    ESQUEMA = ""
    TABLAS: dict = {}
    CLAVES: dict = {}
    ESQUEMA_VERSION = "1"
    NOMBRE = "almacen"

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        nueva = not self.ruta.exists()
        self.con = sqlite3.connect(str(self.ruta), isolation_level=None)   # transacciones explícitas
        self.con.execute("PRAGMA foreign_keys = ON")
        if nueva:
            self.con.executescript(
                "BEGIN;"
                "CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);"
                "CREATE TABLE registro (num INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, "
                "tabla TEXT NOT NULL, clave TEXT NOT NULL, contenido TEXT NOT NULL, hash_previo TEXT NOT NULL, "
                "hash TEXT NOT NULL UNIQUE);"
                + self.ESQUEMA + self._disparadores() + "COMMIT;")
            self.con.execute("INSERT INTO meta VALUES ('tipo', ?), ('esquema_version', ?), ('creada', ?)",
                             (self.NOMBRE, self.ESQUEMA_VERSION, ahora()))
        meta = dict(self.con.execute("SELECT clave, valor FROM meta").fetchall())
        if (meta.get("tipo"), meta.get("esquema_version")) != (self.NOMBRE, self.ESQUEMA_VERSION):
            self.con.close()
            raise ErrorAlmacen(f"{self.ruta.name}: es «{meta.get('tipo')}» v{meta.get('esquema_version')}; "
                               f"se esperaba «{self.NOMBRE}» v{self.ESQUEMA_VERSION}")
        self._en_transaccion = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()

    def cerrar(self):
        self.con.close()

    @classmethod
    def _disparadores(cls) -> str:
        sql = []
        for t in ("meta", "registro", *cls.TABLAS):
            for op in ("UPDATE", "DELETE"):
                sql.append(f"CREATE TRIGGER no_{op.lower()}_{t} BEFORE {op} ON {t} "
                           f"BEGIN SELECT RAISE(ABORT, '{cls.NOMBRE}: solo se añade ({t})'); END;")
        return "\n".join(sql)

    @contextmanager
    def transaccion(self):
        self.con.execute("BEGIN IMMEDIATE")
        self._en_transaccion = True
        try:
            yield self
        except BaseException:
            self.con.execute("ROLLBACK")
            raise
        else:
            self.con.execute("COMMIT")
        finally:
            self._en_transaccion = False

    def _columnas(self, tabla: str, filtro=()) -> tuple:
        columnas = self.TABLAS.get(tabla)
        if columnas is None or not set(filtro) <= set(columnas):
            raise ErrorAlmacen(f"tabla o columnas no permitidas: {tabla} {sorted(filtro)}")
        return columnas

    def insertar(self, tabla: str, fila: dict) -> None:
        if not self._en_transaccion:
            raise ErrorAlmacen("insertar exige una transacción abierta")
        columnas = self._columnas(tabla)
        if set(fila) != set(columnas):
            raise ErrorAlmacen(f"{tabla}: columnas {sorted(fila)} ≠ {sorted(columnas)}")
        self.con.execute(f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})",
                         [fila[c] for c in columnas])
        clave = canonico([fila[c] for c in self.CLAVES.get(tabla, ("id",))])
        contenido = canonico({c: fila[c] for c in columnas})
        previo = self.con.execute("SELECT hash FROM registro ORDER BY num DESC LIMIT 1").fetchone()
        hash_previo = previo[0] if previo else GENESIS
        self.con.execute("INSERT INTO registro (ts, tabla, clave, contenido, hash_previo, hash) VALUES (?,?,?,?,?,?)",
                         (ahora(), tabla, clave, contenido, hash_previo,
                          sha256_texto(hash_previo + tabla + clave + contenido)))

    def existe(self, tabla: str, **filtro) -> bool:
        self._columnas(tabla, filtro)
        donde = " AND ".join(f"{k} = ?" for k in filtro)
        return self.con.execute(f"SELECT 1 FROM {tabla} WHERE {donde} LIMIT 1", list(filtro.values())).fetchone() \
            is not None

    def filas(self, tabla: str, **filtro) -> list:
        cols = self._columnas(tabla, filtro)
        donde = (" WHERE " + " AND ".join(f"{k} = ?" for k in filtro)) if filtro else ""
        orden = " ORDER BY n" if "n" in cols else ""
        cur = self.con.execute(f"SELECT {', '.join(cols)} FROM {tabla}{donde}{orden}", list(filtro.values()))
        return [dict(zip(cols, r)) for r in cur]

    def verificar_cadena(self) -> list:
        """Problemas: cadena rota, filas sin registro, registros sin fila idéntica."""
        problemas, previo, registradas = [], GENESIS, {}
        for num, tabla, clave, contenido, hash_previo, h in self.con.execute(
                "SELECT num, tabla, clave, contenido, hash_previo, hash FROM registro ORDER BY num"):
            if hash_previo != previo:
                problemas.append(f"registro {num}: hash_previo no enlaza con el registro anterior")
            if sha256_texto(hash_previo + tabla + clave + contenido) != h:
                problemas.append(f"registro {num}: el hash no corresponde a su contenido")
            previo = h
            registradas.setdefault(tabla, {})[clave] = contenido
        for tabla, columnas in self.TABLAS.items():
            claves = self.CLAVES.get(tabla, ("id",))
            reales = {}
            for r in self.con.execute(f"SELECT {', '.join(columnas)} FROM {tabla}"):
                fila = dict(zip(columnas, r))
                reales[canonico([fila[c] for c in claves])] = canonico(fila)
            esperadas = registradas.get(tabla, {})
            for k in sorted(set(reales) | set(esperadas)):
                if k not in esperadas:
                    problemas.append(f"{tabla} {k}: fila sin registro en la cadena")
                elif k not in reales:
                    problemas.append(f"{tabla} {k}: registrada pero ausente")
                elif reales[k] != esperadas[k]:
                    problemas.append(f"{tabla} {k}: contenido distinto del registrado")
        return problemas
