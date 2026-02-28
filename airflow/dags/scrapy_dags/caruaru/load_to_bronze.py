import pandas as pd
import s3fs
from trino.dbapi import connect
from airflow.hooks.base import BaseHook

def run_etl():
    print("--- INICIANDO CARGA BRONZE (PYTHON OPERATOR) ---")
    
    # 1. Configurar conexões
    conn = BaseHook.get_connection('minio_s3_connection')
    conn_extra = conn.extra_dejson
    
    # Configuração do FileSystem
    fs = s3fs.S3FileSystem(
        client_kwargs={
            'endpoint_url': conn_extra.get('endpoint_url'),
            'aws_access_key_id': conn.login,
            'aws_secret_access_key': conn.password
        }
    )

    # 2. Caminho de Leitura
    # Ajuste: s3fs.glob às vezes funciona melhor sem o protocolo s3:// se o fs já foi instanciado
    # Mas vamos garantir o padrão correto.
    bucket_name = "bronze"
    prefix = "teste_ingestao"
    search_path = f"{bucket_name}/{prefix}/*.jsonl"
    
    print(f"Procurando arquivos em: {search_path}")
    
    try:
        # Tenta listar (glob retorna lista de caminhos no bucket)
        files = fs.glob(search_path)
        print(f"Arquivos encontrados ({len(files)}): {files}")
    except Exception as e:
        print(f"ERRO ao listar arquivos: {e}")
        raise e

    # --- TRAVA DE SEGURANÇA ---
    # Se não tem arquivos, vamos checar se é erro ou apenas falta de dados
    if not files:
        print("ALERTA: Nenhum arquivo encontrado no caminho especificado.")
        # Se você quer que a DAG falhe quando não tem arquivos (para avisar), descomente a linha abaixo:
        # raise ValueError("Pipeline interrompido: Scrapy rodou mas nenhum arquivo foi encontrado na Landing Zone.")
        return

    # 3. Ler Arquivos
    df_list = []
    valid_files = []
    
    for f in files:
        print(f"Lendo arquivo: {f}")
        try:
            # fs.open requer o caminho relativo ou completo dependendo da versao. 
            # O glob retorna 'bucket/path/file'.
            with fs.open(f, 'rb') as file_obj:
                df_list.append(pd.read_json(file_obj, lines=True))
                valid_files.append(f)
        except Exception as e:
            print(f"Erro ao ler arquivo {f}: {e}")

    if not df_list:
        print("Nenhum dado válido extraído dos arquivos.")
        return
        
    df = pd.concat(df_list)
    
    # Adicionar timestamp de ingestão
    if 'ingestion_at' not in df.columns:
        df['ingestion_at'] = pd.Timestamp.now()

    # 4. Inserir no Trino (Warehouse)
    print("Conectando ao Trino...")
    trino_conn = connect(
        host='trino', # Importante: O Airflow deve conseguir resolver este nome DNS
        port=8080,
        user='admin',
        catalog='iceberg',
        schema='bronze'
    )
    cur = trino_conn.cursor()

    print(f"Inserindo {len(df)} linhas na tabela iceberg.bronze.quotes...")
    
    # Batch insert simples
    for index, row in df.iterrows():
        # Sanitização para evitar quebra de SQL com aspas simples no texto
        texto = str(row['texto']).replace("'", "''")
        autor = str(row['autor']).replace("'", "''")
        url = str(row['url_origem'])
        
        # Formata tags para array SQL
        tags_raw = row.get('tags', [])
        if isinstance(tags_raw, list):
            # Aspas duplas nas tags para escapar corretamente
            tags_list = [f"""'{str(t).replace("'", "''")}'""" for t in tags_raw]
            tags_sql = f"ARRAY[{', '.join(tags_list)}]"
        else:
            tags_sql = "ARRAY[]"

        sql = f"""
            INSERT INTO iceberg.bronze.quotes (texto, autor, tags, url_origem, ingestion_at)
            VALUES (
                '{texto}', 
                '{autor}', 
                {tags_sql}, 
                '{url}',
                TIMESTAMP '{row['ingestion_at'].strftime('%Y-%m-%d %H:%M:%S')}'
            )
        """
        try:
            cur.execute(sql)
        except Exception as e_sql:
            print(f"Erro ao inserir linha {index}: {e_sql}")
            print(f"Query falha: {sql}")
            raise e_sql
    
    trino_conn.commit()
    print("Carga no Trino finalizada com sucesso.")
    
    # 5. Mover para Processed (Evita duplicidade)
    print("Movendo arquivos processados...")
    for f in valid_files:
        # f vem como "bronze/teste_ingestao/arquivo.jsonl"
        file_name = f.split('/')[-1]
        destination = f"{bucket_name}/processed/{prefix}/{file_name}"
        try:
            fs.move(f, destination)
            print(f"Movido: {f} -> {destination}")
        except Exception as e_move:
            print(f"Erro ao mover arquivo {f}: {e_move}")
            # Não damos raise aqui para não rolar rollback do banco, apenas logamos

    print("--- FIM DO PROCESSO ---")
