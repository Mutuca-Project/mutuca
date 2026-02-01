import logging
import os
from io import BytesIO
from typing import Any, Optional

import oci
import requests
from dotenv import load_dotenv
from oci.object_storage import ObjectStorageClient
from scrapy.pipelines.files import FilesPipeline

load_dotenv()


class OCIUploadPDFPipeline(FilesPipeline):
    """
    Pipeline responsável por fazer o download de arquivos PDF e enviá-los para um bucket OCI (Oracle Cloud Infrastructure).
    """

    def __init__(self, *args: Any, **kargs: Any) -> None:
        """
        Inicializa a pipeline, configurando o cliente OCI, nome do bucket, namespace
        e caminho do subdiretório de destino.

        Args:
            *args (Any): Argumentos posicionais passados para a superclasse.
            **kargs (Any): Argumentos nomeados passados para a superclasse.
        """
        self.oci_client = self.__inicialize_oci_client()
        self.bucket_name = os.environ.get("OCI_BUCKET_NAME")
        self.namespace = os.environ.get("OCI_NAMESPACE")
        self.subfolder_path = "municipal-council/parliamentary-allowance"
        super().__init__(*args, **kargs)

    def process_item(self, item, spider) -> dict:
        """
        Processa cada item do Scrapy, baixando e enviando os arquivos especificados
        na chave FILES_URLS_FIELD para o bucket OCI.

        Args:
            item (dict): Item processado pelo Scrapy.
            spider (scrapy.Spider): Instância do spider que processou o item.

        Returns:
            dict: O item original após o processamento.
        """
        if self.FILES_URLS_FIELD in item:
            for file_url in item[self.FILES_URLS_FIELD]:
                download_file_content = self.download_file(file_url)
                if download_file_content:
                    self.upload_to_oci_bucket(item, download_file_content)

        return item

    def download_file(self, file_url) -> Optional[bytes]:
        """
        Faz o download de um arquivo a partir de uma URL.

        Args:
            file_url (str): URL do arquivo a ser baixado.

        Returns:
            return (Optional[bytes]| None): O conteúdo binário do arquivo se o download for bem-sucedido. None, se ocorrer erro ou status HTTP diferente de 200.
        """
        try:
            response = requests.get(file_url)
            if response.status_code == 200:
                return response.content
            else:
                logging.info(
                    f"Failed to download file from {file_url} - Status Code: {response.status_code}"
                )

        except Exception as error:
            logging.error(f"Error downloading file from {file_url}: {error}")

        return None

    def upload_to_oci_bucket(self, item, file_content) -> None:
        """
        Faz o upload de um arquivo PDF para o bucket da OCI.

        Args:
            item (dict): Item contendo metadados, incluindo o nome do arquivo.
            file_content (bytes): Conteúdo do arquivo a ser enviado.
        """
        file_name = item.get("file_id", "default_file_name")
        object_name = f"{self.subfolder_path}/{file_name}"

        try:
            self.oci_client.put_object(
                namespace_name=self.namespace,
                bucket_name=self.bucket_name,
                object_name=object_name,
                put_object_body=BytesIO(file_content),
                content_type="application/pdf",
            )
            logging.info(
                f"File '{file_name}' has been uploaded to bucket '{self.bucket_name}'."
            )
        except oci.exceptions.ServiceError as error:
            logging.error(f"Error uploading file {file_name} to OCI Bucket: {error}")

    def __inicialize_oci_client(self) -> ObjectStorageClient:
        """
        Inicializa o cliente da OCI usando variáveis de ambiente.

        Returns:
            Cliente configurado para uso.

        Raises:
            Exception: Caso ocorra erro na inicialização do cliente.
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
            logging.error(f"Error initializing OCI client: {error}")
            raise
