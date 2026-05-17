"""
POC — Issue #56: Validar mecanismo de branch switching no Trino + Nessie REST catalog.
Testa três abordagens em ordem de preferência.
Execute com: python poc_session_properties.py
"""
import os
import trino
from pynessie import init
from pyiceberg.catalog.rest import RestCatalog
from pynessie import init
from dotenv import load_dotenv
load_dotenv()

NESSIE_ENDPOINT = "http://localhost:19120/api/v1"
TRINO_HOST = "localhost"
TRINO_PORT = 8080

BRANCH = "test_pyiceberg_poc"
MINIO_USER = os.getenv("MINIO_ROOT_USER")      # do .env
MINIO_PASS = os.getenv("MINIO_ROOT_PASSWORD")      # do .env

nessie = init(config_dict={"endpoint": NESSIE_ENDPOINT})


def setup():
    print(f"\n[SETUP] Criando branch '{BRANCH}'...")
    try:
        ref = nessie.get_reference("main")
        nessie.create_branch(BRANCH, ref="main", hash_on_ref=ref.hash_)
        print(f"[SETUP] Branch '{BRANCH}' criada. ✅")
    except Exception as e:
        print(f"[SETUP] Aviso: {e}")


def teardown():
    print(f"\n[TEARDOWN] Deletando branch '{BRANCH}'...")
    try:
        ref = nessie.get_reference(BRANCH)
        nessie.delete_branch(BRANCH, hash_=ref.hash_)
        print(f"[TEARDOWN] Branch '{BRANCH}' deletada. ✅")
    except Exception as e:
        print(f"[TEARDOWN] Erro: {e}")


def commits_on_branch():
    try:
        logs = list(nessie.get_log(BRANCH))
        return len(logs)
    except Exception:
        return 0


# ─── ABORDAGEM 1: iceberg.nessie_reference_name (conector nessie legado) ──────
def test_abordagem_1():
    print("\n" + "="*60)
    print("ABORDAGEM 1: session_properties iceberg.nessie_reference_name")
    print("="*60)
    antes = commits_on_branch()
    try:
        conn = trino.dbapi.connect(
            host=TRINO_HOST,
            port=TRINO_PORT,
            user="admin",
            session_properties={"iceberg.nessie_reference_name": BRANCH}
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchall()
        depois = commits_on_branch()
        if depois > antes:
            print(f"✅ FUNCIONOU — {depois - antes} commit(s) novo(s) em '{BRANCH}'")
            return True
        else:
            print("⚠️  Sessão aberta sem erro, mas nenhum commit na branch.")
            print("   A propriedade pode ser ignorada silenciosamente.")
            return False
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False


# ─── ABORDAGEM 2: namespace com branch como prefixo ───────────────────────────
def test_abordagem_2():
    print("\n" + "="*60)
    print("ABORDAGEM 2: namespace prefixado — iceberg.\"BRANCH.schema\".table")
    print("="*60)
    antes = commits_on_branch()
    try:
        conn = trino.dbapi.connect(
            host=TRINO_HOST,
            port=TRINO_PORT,
            user="admin",
        )
        cur = conn.cursor()
        # Nessie REST catalog expõe branches como prefixo no namespace
        cur.execute(f'SHOW SCHEMAS FROM iceberg')
        schemas = cur.fetchall()
        print(f"   Schemas disponíveis: {schemas[:5]}")

        # Tentar acessar namespace com branch como prefixo
        cur.execute(f'SHOW TABLES FROM iceberg."{BRANCH}.bronze"')
        tabelas = cur.fetchall()
        print(f"   Tabelas em '{BRANCH}.bronze': {tabelas}")

        depois = commits_on_branch()
        print(f"   Commits antes/depois: {antes}/{depois}")
        return True
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False


# ─── ABORDAGEM 3: header via requests (PyIceberg direto) ──────────────────────
def test_abordagem_3():
    print("\n" + "="*60)
    print("ABORDAGEM 3: PyIceberg REST catalog com prefix por instância")
    print("="*60)

    nessie = init(config_dict={"endpoint": "http://localhost:19120/api/v1"})
    ref = nessie.get_reference("main")

    try:
        ref_existente = nessie.get_reference(BRANCH)
        nessie.delete_branch(BRANCH, hash_=ref_existente.hash_)
        print(f"   Branch órfã '{BRANCH}' removida.")
    except Exception:
        pass  # Não existia, tudo certo

    nessie.create_branch(BRANCH, ref="main", hash_on_ref=ref.hash_)

    try:
        from pyiceberg.catalog.rest import RestCatalog
        catalog = RestCatalog(
            "nessie_branch",
            **{
                "uri": "http://localhost:19120/iceberg/",
                "warehouse": "s3://warehouse/",
                "prefix": BRANCH,
                "s3.endpoint": "http://localhost:9000",
                "s3.access-key-id": MINIO_USER,        # ajuste ao seu .env
                "s3.secret-access-key": MINIO_PASS,  # ajuste ao seu .env
                "s3.path-style-access": "true",
            }
        )
        namespaces = catalog.list_namespaces()
        print(f"   Namespaces via branch '{BRANCH}': {namespaces}")
        print("✅ PyIceberg REST catalog com prefix funciona.")
        ref2 = nessie.get_reference(BRANCH)
        nessie.delete_branch(BRANCH, hash_=ref2.hash_)
        print(f"Branch {ref2.hash_} deletada.")
        return True
    except ImportError:
        print("⚠️  pyiceberg não instalado neste venv. Instale com: uv add pyiceberg")
        return False
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False


if __name__ == "__main__":
    setup()
    r1 = test_abordagem_1()
    r2 = test_abordagem_2()
    r3 = test_abordagem_3()
    teardown()

    print("\n" + "="*60)
    print("RESULTADO FINAL")
    print("="*60)
    print(f"Abordagem 1 (nessie_reference_name): {'✅' if r1 else '❌'}")
    print(f"Abordagem 2 (namespace prefixado):    {'✅' if r2 else '❌'}")
    print(f"Abordagem 3 (PyIceberg + prefix):     {'✅' if r3 else '❌'}")
