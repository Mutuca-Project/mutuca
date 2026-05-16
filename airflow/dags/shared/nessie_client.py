"""
nessie_client.py — Operações de lifecycle de branches no Nessie.

Usado pelo factory.py para isolar cada execução de ingestão numa branch
dedicada (ADR 007). Também funciona como CLI standalone para testes.

Variável de ambiente:
    NESSIE_ENDPOINT: URL base do servidor Nessie.
                     Padrão: http://localhost:19120/api/v1
                     Em produção Docker: http://lakehouse-nessie:19120/api/v1

Fluxo de ingestão esperado (ADR 007):
    create_branch(branch_name)
        → load_iceberg (escreve na branch via PyIceberg)
        → dbt_test (valida na branch)
        → merge_to_main(branch_name) | delete_branch(branch_name)
"""

import logging
import os
import sys

from pynessie import init
from pynessie.error import NessieConflictException, NessieNotFoundException

log = logging.getLogger(__name__)

NESSIE_ENDPOINT = os.getenv("NESSIE_ENDPOINT", "http://localhost:19120/api/v1")


def _client():
    """Retorna um cliente pynessie inicializado."""
    return init(config_dict={"endpoint": NESSIE_ENDPOINT})


# ---------------------------------------------------------------------------
# Operações públicas
# ---------------------------------------------------------------------------


def get_branch_hash(branch_name: str) -> str:
    """Retorna o hash HEAD da branch. Lança exceção se não existir."""
    ref = _client().get_reference(branch_name)
    log.info("hash '%s': %s", branch_name, ref.hash_)
    return ref.hash_


def create_branch(branch_name: str, from_ref: str = "main") -> str:
    """
    Cria uma branch a partir de from_ref.

    Se a branch já existir, apenas loga um aviso e continua
    (idempotência para reexecuções de DAG).

    Retorna o hash HEAD da branch após a criação.
    """
    client = _client()
    try:
        source = client.get_reference(from_ref)
        client.create_branch(branch_name, ref=from_ref, hash_on_ref=source.hash_)
        log.info("branch '%s' criada a partir de '%s' (%s)", branch_name, from_ref, source.hash_)
    except NessieConflictException:
        log.warning("branch '%s' já existe — continuando.", branch_name)
    return get_branch_hash(branch_name)


def merge_to_main(branch_name: str) -> None:
    """
    Faz merge da branch para main.

    Chamado apenas após dbt_test bem-sucedido (ADR 007).
    A deleção da branch após o merge é responsabilidade de quem chama.
    """
    _client().merge(branch_name, "main")
    log.info("branch '%s' mergeada para main.", branch_name)


def delete_branch(branch_name: str) -> None:
    """
    Deleta a branch. Idempotente: se não existir, apenas loga.

    Deve ser chamado em ambos os caminhos do DAG (sucesso e falha)
    para evitar acúmulo de branches órfãs (ADR 007 — Consequências).
    """
    client = _client()
    try:
        ref = client.get_reference(branch_name)
        client.delete_branch(branch_name, hash_=ref.hash_)
        log.info("branch '%s' deletada.", branch_name)
    except NessieNotFoundException:
        log.warning("branch '%s' não encontrada — nada a deletar.", branch_name)


# ---------------------------------------------------------------------------
# CLI standalone (para testes e operações manuais)
# ---------------------------------------------------------------------------

_USAGE = """
Uso: python nessie_client.py <comando> [args]

Comandos:
  create <branch> [from_ref]   Cria branch (padrão: a partir de main)
  hash   <branch>              Exibe o hash HEAD da branch
  merge  <branch>              Faz merge de <branch> para main
  delete <branch>              Deleta a branch
"""


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) < 3:
        print(_USAGE)
        sys.exit(1)

    cmd, branch = sys.argv[1], sys.argv[2]

    if cmd == "create":
        from_ref = sys.argv[3] if len(sys.argv) > 3 else "main"
        h = create_branch(branch, from_ref)
        print(f"✅ branch '{branch}' pronta. hash={h}")

    elif cmd == "hash":
        print(get_branch_hash(branch))

    elif cmd == "merge":
        merge_to_main(branch)
        print(f"✅ branch '{branch}' mergeada para main.")

    elif cmd == "delete":
        delete_branch(branch)
        print(f"✅ branch '{branch}' deletada.")

    else:
        print(f"❌ Comando desconhecido: '{cmd}'{_USAGE}")
        sys.exit(1)


if __name__ == "__main__":
    _main()
