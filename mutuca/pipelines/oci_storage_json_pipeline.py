import json
import os
from io import BytesIO

import oci
from dotenv import load_dotenv

load_dotenv()


class OCIUploadJSONPipeline:
    """
    Pipeline de exportação para o Oracle Cloud Infrastructure (OCI) que acumula itens coletados por um spider
    e, ao final da execução, envia um arquivo JSON contendo todos os dados para um bucket especificado.

    A classe utiliza variáveis de ambiente para configurar o cliente OCI e determina a pasta de destino no bucket
    para armazenar o arquivo JSON.

    Attributes:
        oci_client (ObjectStorageClient): Cliente OCI inicializado para interação com o Object Storage.
        bucket_name (str): Nome do bucket configurado via variável de ambiente.
        namespace (str): Namespace do bucket no OCI.
        subfolder_path (str): Caminho dentro do bucket onde o arquivo será armazenado.
        items (list): Lista de itens acumulados durante a execução do spider.
    """

    def __init__(self):
        self.oci_client = self.__initialize_oci_client()
        self.bucket_name = os.environ.get("OCI_BUCKET_NAME")
        self.namespace = os.environ.get("OCI_NAMESPACE")
        self.subfolder_path = "cityhall/public_works"
        self.items = []  # Lista para armazenar os itens coletados

    def process_item(self, item, spider):
        """
        Processa cada item coletado pelo spider, adicionando-o à lista interna de itens.

        Args:
            item (dict): Item de dados coletado.
            spider (scrapy.Spider): Instância do spider responsável pela coleta.

        Returns:
            dict: O item processado, retornado para manter o fluxo do pipeline.
        """
        self.items.append(dict(item))  # Armazena o item coletado
        return item

    def close_spider(self, spider):
        """
        Executado ao final da execução do spider. Converte a lista de itens para JSON
        e envia o conteúdo como um único arquivo para o bucket OCI.

        Args:
            spider (scrapy.Spider): Instância do spider que foi executado.
        """

        file_name = "caruaru_public_works.json"
        object_name = f"{self.subfolder_path}/{file_name}"

        # Convertendo os itens acumulados para JSON
        json_content = json.dumps(self.items, ensure_ascii=False, indent=4)

        try:
            self.oci_client.put_object(
                namespace_name=self.namespace,
                bucket_name=self.bucket_name,
                object_name=object_name,
                put_object_body=BytesIO(json_content.encode("utf-8")),
                content_type="application/json",
            )
            print(f"Arquivo '{file_name}' enviado para o bucket '{self.bucket_name}'.")
        except oci.exceptions.ServiceError as error:
            print(f"Erro ao enviar o arquivo {file_name} para o OCI Bucket: {error}")

    def __initialize_oci_client(self):
        """
        Inicializa o cliente OCI usando as variáveis de ambiente para autenticação.

        Returns:
            ObjectStorageClient: Cliente OCI autenticado.

        Raises:
            Exception: Caso ocorra algum erro ao carregar as configurações ou iniciar o cliente.
        """
        try:
            config = {
                "user": os.environ.get("OCI_USER"),
                "fingerprint": os.environ.get("OCI_FINGERPRINT"),
                "tenancy": os.environ.get("OCI_TENANCY"),
                "key_file": os.environ.get("OCI_KEY_FILE_PATH"),
                "region": os.environ.get("OCI_REGION"),
            }
            return oci.object_storage.ObjectStorageClient(config)
        except Exception as error:
            print(f"Erro ao inicializar o cliente OCI: {error}")
            raise
