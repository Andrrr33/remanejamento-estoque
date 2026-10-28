"""Cadastro, senhas e sessões persistidos no SQLite."""
from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from typing import Any

from banco_local import conectar

ITERATIONS = 600_000


def normalizar_usuario(username: str) -> str:
    limpo = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9]{3,32}", limpo, flags=re.ASCII):
        raise ValueError("Use de 3 a 32 letras sem acento ou números no nome de usuário.")
    return limpo.upper()


def validar_senha(senha: str) -> None:
    if not 12 <= len(senha) <= 128 or not senha.strip():
        raise ValueError("A senha precisa ter de 12 a 128 caracteres.")


def hash_senha(senha: str) -> str:
    salt = secrets.token_hex(16)
    chave = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"{salt}${chave.hex()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    if not isinstance(senha, str) or len(senha) > 128:
        return False
    salt, chave = armazenado.split("$")
    calculado = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(salt), ITERATIONS)
    return hmac.compare_digest(calculado.hex(), chave)


def _conta(row: sqlite3.Row) -> dict[str, Any]:
    chaves = ("id", "username", "perfil", "trocar_senha", "versao_senha", "versao_guia")
    return {chave: row[chave] for chave in chaves}


def cadastrar(username: str, senha: str) -> None:
    usuario = normalizar_usuario(username)
    validar_senha(senha)
    senha_hash = hash_senha(senha)
    with conectar() as db:
        if db.execute("SELECT 1 FROM usuarios WHERE username = ?", (usuario,)).fetchone():
            raise ValueError("Este nome de usuário já está em uso.")
        db.execute(
            "INSERT INTO usuarios (username, senha_hash) VALUES (?, ?)",
            (usuario, senha_hash),
        )


def autenticar(username: str, senha: str) -> dict[str, Any] | None:
    try:
        usuario = normalizar_usuario(username)
    except ValueError:
        return None
    with conectar() as db:
        row = db.execute("SELECT * FROM usuarios WHERE username = ?", (usuario,)).fetchone()
        if not row:
            verificar_senha(senha, "00" * 16 + "$" + "00" * 32)
            return None
        if row["bloqueado_ate"] > time.time():
            return None
        if not verificar_senha(senha, row["senha_hash"]):
            falhas = row["falhas"] + 1
            bloqueio = time.time() + 900 if falhas >= 5 else 0
            db.execute(
                "UPDATE usuarios SET falhas = ?, bloqueado_ate = ? WHERE id = ?",
                (0 if falhas >= 5 else falhas, bloqueio, row["id"]),
            )
            return None
        db.execute("UPDATE usuarios SET falhas = 0, bloqueado_ate = 0 WHERE id = ?", (row["id"],))
        return _conta(row)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def criar_sessao(usuario_id: int, versao_senha: int) -> str:
    token = secrets.token_urlsafe(32)
    agora = time.time()
    with conectar() as db:
        db.execute("DELETE FROM sessoes WHERE atividade < ?", (agora - 300,))
        db.execute(
            "INSERT INTO sessoes VALUES (?, ?, ?, ?)",
            (_hash_token(token), usuario_id, versao_senha, agora),
        )
    return token


def validar_sessao(token: str | None) -> dict[str, Any] | None:
    if not isinstance(token, str) or not 20 <= len(token) <= 128:
        return None
    with conectar() as db:
        row = db.execute(
            """
            SELECT u.*
            FROM usuarios u
            JOIN sessoes s ON s.usuario_id = u.id
            WHERE s.token_hash = ?
              AND s.atividade > ?
              AND s.versao_senha = u.versao_senha
            """,
            (_hash_token(token), time.time() - 300),
        ).fetchone()
    return _conta(row) if row else None


def tocar_sessao(token: str | None) -> bool:
    if not validar_sessao(token) or token is None:
        return False
    agora = time.time()
    with conectar() as db:
        db.execute(
            "UPDATE sessoes SET atividade = ? WHERE token_hash = ? AND atividade > ?",
            (agora, _hash_token(token), agora - 300),
        )
    return True


def revogar_sessao(token: str | None) -> None:
    if token:
        with conectar() as db:
            db.execute("DELETE FROM sessoes WHERE token_hash = ?", (_hash_token(token),))


def exigir_usuario(admin: bool = False, usuario_id: int | None = None) -> dict[str, Any]:
    import streamlit as st

    conta = validar_sessao(st.session_state.get("auth_token"))
    if (
        not conta
        or (admin and conta["perfil"] != "admin")
        or (usuario_id is not None and conta["id"] != usuario_id)
    ):
        raise PermissionError("Sua sessão não permite esta operação.")
    return conta


def trocar_senha(usuario_id: int, senha_atual: str, nova_senha: str) -> bool:
    exigir_usuario(usuario_id=usuario_id)
    validar_senha(nova_senha)
    with conectar() as db:
        row = db.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        if not row or not verificar_senha(senha_atual, row["senha_hash"]):
            return False
        db.execute(
            """
            UPDATE usuarios
            SET senha_hash = ?, trocar_senha = 0, versao_senha = versao_senha + 1,
                falhas = 0, bloqueado_ate = 0
            WHERE id = ?
            """,
            (hash_senha(nova_senha), usuario_id),
        )
        db.execute("DELETE FROM sessoes WHERE usuario_id = ?", (usuario_id,))
    return True


def solicitar_recuperacao(username: str) -> None:
    try:
        usuario = normalizar_usuario(username)
    except ValueError:
        return
    with conectar() as db:
        row = db.execute("SELECT id FROM usuarios WHERE username = ?", (usuario,)).fetchone()
        if not row:
            return
        pendente = db.execute(
            "SELECT 1 FROM recuperacoes WHERE usuario_id = ? AND status = 'pendente'",
            (row["id"],),
        ).fetchone()
        if not pendente:
            db.execute(
                "INSERT INTO recuperacoes (usuario_id, data) VALUES (?, ?)",
                (row["id"], datetime.now().isoformat()),
            )


def recuperacoes_pendentes() -> list[tuple[int, str, datetime]]:
    exigir_usuario(admin=True)
    with conectar() as db:
        rows = db.execute(
            """
            SELECT r.id, u.username, r.data
            FROM recuperacoes r
            JOIN usuarios u ON u.id = r.usuario_id
            WHERE r.status = 'pendente'
            ORDER BY r.id
            """
        ).fetchall()
    return [(r["id"], r["username"], datetime.fromisoformat(r["data"])) for r in rows]


def emitir_senha_temporaria(pedido_id: int, admin_id: int) -> str | None:
    exigir_usuario(admin=True, usuario_id=admin_id)
    with conectar() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM recuperacoes WHERE id = ? AND status = 'pendente'",
            (pedido_id,),
        ).fetchone()
        if not row:
            return None
        senha = secrets.token_urlsafe(15)
        db.execute(
            """
            UPDATE usuarios
            SET senha_hash = ?, trocar_senha = 1, versao_senha = versao_senha + 1,
                falhas = 0, bloqueado_ate = 0
            WHERE id = ?
            """,
            (hash_senha(senha), row["usuario_id"]),
        )
        db.execute("DELETE FROM sessoes WHERE usuario_id = ?", (row["usuario_id"],))
        db.execute("UPDATE recuperacoes SET status = 'atendido' WHERE id = ?", (pedido_id,))
    return senha


def cancelar_recuperacao(pedido_id: int, admin_id: int) -> bool:
    exigir_usuario(admin=True, usuario_id=admin_id)
    with conectar() as db:
        cursor = db.execute(
            "UPDATE recuperacoes SET status = 'cancelado' WHERE id = ? AND status = 'pendente'",
            (pedido_id,),
        )
        return bool(cursor.rowcount)


def marcar_guia_visto(usuario_id: int, versao: int) -> None:
    exigir_usuario(usuario_id=usuario_id)
    with conectar() as db:
        db.execute("UPDATE usuarios SET versao_guia = ? WHERE id = ?", (versao, usuario_id))


def preparar_contas() -> None:
    contas_demo = [("ADMINDEMO", "admin"), ("COMPRASDEMO", "usuario")]
    with conectar() as db:
        for username, perfil in contas_demo:
            existe = db.execute("SELECT 1 FROM usuarios WHERE username = ?", (username,)).fetchone()
            if not existe:
                db.execute(
                    "INSERT INTO usuarios (username, senha_hash, perfil) VALUES (?, ?, ?)",
                    (username, hash_senha("Portfolio2026!"), perfil),
                )


preparar_contas()
