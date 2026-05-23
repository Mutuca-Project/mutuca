#!/bin/bash
set -euo pipefail

# =========================================================
# Diretório alvo (mesmo valor de RFB_CNPJ_HD_PATH no .env)
# =========================================================
export HD_PATH="/media/datafixer/Expansion/DATALAKE/RAW/receita_federal_cnpj"
mkdir -p "$HD_PATH"

echo "Gerando arquivos em: $HD_PATH"
echo

# =========================================================
# Empresas (7 colunas, sem header, latin-1, separador ;)
# =========================================================
python3 - <<'EOF'
import csv, random, os

hd_path = os.environ["HD_PATH"]
caminho = f"{hd_path}/Empresas0.csv"

with open(caminho, "w", encoding="latin-1", newline="") as f:
    writer = csv.writer(f, delimiter=";")
    for i in range(1000):
        writer.writerow([
            str(random.randint(10000000, 99999999)),  # cnpj_basico
            f"EMPRESA TESTE {i} LTDA",                 # razao_social
            "2062",                                   # natureza_juridica (Ltda)
            "49",                                     # qualificacao_responsavel
            f"{random.randint(0,1000000)},00",        # capital_social
            "05",                                     # porte_empresa
            "",                                       # ente_federativo_responsavel
        ])

print(f"Criado: {caminho}")
EOF

# =========================================================
# Estabelecimentos (30 colunas)
# =========================================================
python3 - <<'EOF'
import csv, random, os

hd_path = os.environ["HD_PATH"]
caminho = f"{hd_path}/Estabelecimentos0.csv"
ufs = ["PE", "BA", "CE", "PB", "AL"]

with open(caminho, "w", encoding="latin-1", newline="") as f:
    writer = csv.writer(f, delimiter=";")
    for i in range(1000):
        cnpj = str(random.randint(10000000, 99999999))
        cnae = "9491000" if i % 5 == 0 else str(random.randint(1000000, 9999999))

        writer.writerow([
            cnpj, "0001", "00",           # cnpj_basico, ordem, dv
            "1",                           # matriz
            f"FANTASIA {i}",               # nome_fantasia
            "2",                           # situacao_cadastral (Ativa)
            "20230101",                    # data_situacao
            "00",                          # motivo
            "", "", "20200101",            # cidade_ext, pais, data_inicio
            cnae,                          # cnae_principal
            "",                            # cnae_secundaria
            "RUA",
            f"LOGRADOURO {i}",
            str(i),
            "",
            "BAIRRO",
            f"{random.randint(10000,99999):05d}-{random.randint(100,999)}",
            random.choice(ufs),
            str(random.randint(1000, 9999)),  # municipio
            "81",                              # ddd1
            str(random.randint(30000000, 39999999)),  # telefone1
            "", "", "", "", "",               # ddd2, tel2, ddd_fax, fax, email
            "", "",                           # situacao_especial, data_especial
        ])

print(f"Criado: {caminho}")
EOF

# =========================================================
# Sócios (11 colunas)
# =========================================================
python3 - <<'EOF'
import csv, random, os

hd_path = os.environ["HD_PATH"]
caminho = f"{hd_path}/Socios0.csv"

nomes = [
    "JOAO DA SILVA",
    "MARIA SANTOS",
    "PASTOR JOSE FERREIRA",
    "BISPO ANTONIO",
]

with open(caminho, "w", encoding="latin-1", newline="") as f:
    writer = csv.writer(f, delimiter=";")
    for i in range(1000):
        writer.writerow([
            str(random.randint(10000000, 99999999)),  # cnpj_basico
            "2",                                      # identificador_socio (PF)
            random.choice(nomes),                     # nome_socio
            f"***{random.randint(100,999)}***",       # cpf mascarado
            "49",                                     # qualificacao
            "20200101",                               # data_entrada
            "105",                                    # pais (Brasil)
            "",                                       # representante
            "",                                       # nome_rep
            "00",                                     # qualificacao_rep
            "5",                                      # faixa_etaria
        ])

print(f"Criado: {caminho}")
EOF

echo
echo "Processo concluído com sucesso."
