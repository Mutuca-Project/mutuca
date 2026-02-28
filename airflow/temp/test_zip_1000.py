import os
import zipfile
import time
from lxml import etree 

AMOSTRA_DIR = "/home/datafixer/teste_zip_1000"
TOTAL_ARQUIVOS_PROJETO = 7_000_000
ESTADOS_NE = {'AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE'}
STATUS_POS_VALIDOS = {'CONCLUIDO', 'EM_ANDAMENTO'}

def analisar_lattes(xml_bytes, id_lattes):
    """
    Faz o parsing do XML em memória, busca as tags de interesse e aplica o filtro.
    Retorna (True, dados_extraidos) se passar no filtro, ou (False, None) caso contrário.
    """
    root = etree.fromstring(xml_bytes)
    
    # ---------------------------------------------------------
    # 1. FILTRO DE LOCALIDADE (NORDESTE)
    # ---------------------------------------------------------
    endereco = root.find('.//ENDERECO-PROFISSIONAL')
    if endereco is None:
        return False, None
    
    uf = endereco.get('UF')
    if uf not in ESTADOS_NE:
        return False, None

    # ---------------------------------------------------------
    # 2. FILTRO DE TITULAÇÃO (PÓS-GRADUADO)
    # ---------------------------------------------------------
    # Busca todas as tags de pós-graduação de uma vez
    tags_pos = root.xpath('.//MESTRADO | .//DOUTORADO | .//POS-DOUTORADO')
    
    eh_pos_graduado = False
    for tag in tags_pos:
        status = tag.get('STATUS-DO-CURSO')
        if status in STATUS_POS_VALIDOS:
            eh_pos_graduado = True
            break # Já validou, não precisa olhar as outras titulações

    if not eh_pos_graduado:
        return False, None

    # ---------------------------------------------------------
    # 3. EXTRAÇÃO DAS TAGS DE INTERESSE (Simulação de Carga)
    # Se chegou aqui, passou nos filtros. Agora simulamos a 
    # extração do restante para compor a tabela Bronze (Parquet).
    # ---------------------------------------------------------
    
    # Dados Gerais (ex: pegando nome)
    dados_gerais = root.find('.//DADOS-GERAIS')
    nome = dados_gerais.get('NOME-COMPLETO') if dados_gerais is not None else "N/A"
    
    # Contagem de Atuações, Projetos e Produções (simulando parsing mais profundo)
    qtd_atuacoes = len(root.xpath('.//ATUACAO-PROFISSIONAL'))
    qtd_projetos = len(root.xpath('.//PROJETO-DE-PESQUISA'))
    qtd_producoes = len(root.xpath('.//ARTIGO-PUBLICADO'))

    # Montamos um dicionário simulando a linha que iria para o DataFrame/Parquet
    registro_extraido = {
        'id_lattes': id_lattes,
        'nome': nome,
        'uf_atuacao': uf,
        'qtd_atuacoes': qtd_atuacoes,
        'qtd_projetos': qtd_projetos,
        'qtd_producoes': qtd_producoes
    }
    
    return True, registro_extraido

def executar_poc():
    arquivos_zip = [f for f in os.listdir(AMOSTRA_DIR) if f.endswith('.zip')]
    if not arquivos_zip:
        print("Nenhum arquivo ZIP encontrado na pasta de amostra.")
        return

    print(f"Iniciando processamento de {len(arquivos_zip)} arquivos de amostra...")
    
    start_time = time.time()
    perfis_ingeridos = 0
    erros = 0

    for arquivo in arquivos_zip:
        caminho_zip = os.path.join(AMOSTRA_DIR, arquivo)
        id_lattes = arquivo.replace('.zip', '')
        caminho_xml_interno = f"{id_lattes}.xml"
        try:
            with zipfile.ZipFile(caminho_zip, 'r') as zf:
                with zf.open(caminho_xml_interno) as xml_file:
                    xml_bytes = xml_file.read()
                    # Chama a função pesada
                    aprovado, dados = analisar_lattes(xml_bytes, id_lattes)
                    
                    if aprovado:
                        perfis_ingeridos += 1
                        # No pipeline real, adicionaríamos 'dados' a uma lista
                        # para depois converter em Pandas e salvar em Parquet.
                        
        except Exception as e:
            erros += 1

    end_time = time.time()
    tempo_total_segundos = end_time - start_time
    
    # Projeções matemáticas
    tempo_por_arquivo = tempo_total_segundos / len(arquivos_zip)
    tempo_projetado_total_segundos = tempo_por_arquivo * TOTAL_ARQUIVOS_PROJETO
    
    print("\n" + "="*50)
    print("RESULTADOS DO BENCHMARK (REALISTA)")
    print("="*50)
    print(f"Tempo para processar {len(arquivos_zip)} ZIPs: {tempo_total_segundos:.2f} segundos")
    print(f"Pós-graduados do Nordeste (Filtro Passou): {perfis_ingeridos}")
    print(f"Erros (Zips corrompidos/ausentes): {erros}")
    print("\nPROJEÇÃO PARA 7 MILHÕES DE ARQUIVOS (Single Thread):")
    print(f"Tempo estimado: {tempo_projetado_total_segundos / 3600:.2f} horas")
    print("="*50)

if __name__ == "__main__":
    executar_poc()
