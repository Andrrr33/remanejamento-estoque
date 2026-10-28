"""Banco SQLite local para persistência de usuários, sessões e solicitações."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

DB_PATH = Path(__file__).resolve().parent / "dados" / "portfolio.sqlite3"


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def preparar_schema() -> None:
    with conectar() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                perfil TEXT NOT NULL DEFAULT 'usuario',
                trocar_senha INTEGER NOT NULL DEFAULT 0,
                versao_senha INTEGER NOT NULL DEFAULT 1,
                versao_guia INTEGER NOT NULL DEFAULT 0,
                falhas INTEGER NOT NULL DEFAULT 0,
                bloqueado_ate REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessoes (
                token_hash TEXT PRIMARY KEY,
                usuario_id INTEGER REFERENCES usuarios(id),
                versao_senha INTEGER NOT NULL,
                atividade REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recuperacoes (
                id INTEGER PRIMARY KEY,
                usuario_id INTEGER REFERENCES usuarios(id),
                data TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pendente'
            );
            CREATE TABLE IF NOT EXISTS solicitacoes (
                id INTEGER PRIMARY KEY,
                Data_sugestao TEXT NOT NULL,
                Execucao_ID TEXT NOT NULL,
                SKU TEXT NOT NULL,
                Prod_pai TEXT NOT NULL,
                Cor TEXT NOT NULL,
                Filial_origem_ID INTEGER NOT NULL,
                Filial_destino_ID INTEGER NOT NULL,
                Quantidade_sugerida INTEGER NOT NULL CHECK(Quantidade_sugerida > 0),
                Status TEXT NOT NULL,
                Observacoes TEXT NOT NULL,
                CHECK(Filial_origem_ID != Filial_destino_ID)
            );
            CREATE TABLE IF NOT EXISTS metadados (
                chave TEXT PRIMARY KEY,
                valor TEXT
            );
            """
        )


preparar_schema()
