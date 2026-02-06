import sys
import os
from pynessie import init
from pynessie.error import NessieConflictException

# Configuração
# Pynessie detecta automaticamente se deve usar v1 ou v2 baseado na URL
NESSIE_ENDPOINT = os.getenv("NESSIE_ENDPOINT", "http://localhost:19120/api/v1")

def create_branch_sdk(new_branch_name, source_ref="main"):
    print(f"🔌 Conectando ao Nessie em: {NESSIE_ENDPOINT}")
    
    # Inicializa o cliente (Autenticação None por padrão para Nessie local)
    client = init(config_dict={"endpoint": NESSIE_ENDPOINT})

    try:
        # 1. Obter o hash atual da origem (main)
        print(f"🔍 Buscando hash da referência '{source_ref}'...")
        source_reference = client.get_reference(source_ref)
        source_hash = source_reference.hash_
        print(f"ℹ️  Hash de origem: {source_hash}")

        # 2. Criar a nova branch
        print(f"🚀 Criando branch '{new_branch_name}'...")
        client.create_branch(new_branch_name, ref=source_ref, hash_on_ref=source_hash)
        
        print(f"✅ SUCESSO! Branch '{new_branch_name}' criada.")

    except NessieConflictException:
        print(f"⚠️  Aviso: A branch '{new_branch_name}' já existe ou o hash de origem mudou.")
    except Exception as e:
        print(f"❌ Erro Crítico: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python nessie_client.py <nome_da_nova_branch> [branch_origem]")
        sys.exit(1)
    
    branch_name = sys.argv[1]
    source = sys.argv[2] if len(sys.argv) > 2 else "main"
    
    create_branch_sdk(branch_name, source)
