import os
import zipfile

import requests
from twisted.internet import threads


class ReceitaFederalLocalZipExtractorPipeline:
    def process_item(self, item, spider):
        # Desvia a operação de I/O pesada (disco/rede) para uma thread separada.
        # Isso impede que o reactor assíncrono do Scrapy trave.
        return threads.deferToThread(self._download_and_extract, item, spider)

    def _download_and_extract(self, item, spider):
        file_url = item["file_url"]
        file_name = item["file_name"]
        target_dir = item["target_dir"]

        # Garante que o diretório no HD externo exista
        # Este projeto, a princípio, armazena os dados em um HD externo
        # TODO: alterar a lógica de armazenamenot para o Airflow
        os.makedirs(target_dir, exist_ok=True)
        zip_path = os.path.join(target_dir, file_name)

        spider.logger.info(f"Iniciando stream de download para: {file_name}")

        try:
            # Download em blocos de 8KB, direto do buffer da rede para o disco externo
            with requests.get(file_url, stream=True) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            spider.logger.info(f"Extraindo: {file_name}")

            # Descompacta os arquivos contidos no zip para a pasta target
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(target_dir)

            spider.logger.info(f"Extração finalizada em: {target_dir}")

        except Exception as e:
            spider.logger.error(f"Erro ao processar {file_name}: {e}")

        finally:
            # Apagar o .zip para não duplicar o uso de espaço no HD
            if os.path.exists(zip_path):
                os.remove(zip_path)
                spider.logger.info(f"ZIP descartado com sucesso: {file_name}")

        return item
