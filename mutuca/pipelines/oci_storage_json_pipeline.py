import os
import json
from io import BytesIO
from dotenv import load_dotenv
import oci

load_dotenv()

class OCIUploadJSONPipeline:
    def __init__(self):
        self.oci_client = self.__initialize_oci_client()
        self.bucket_name = os.environ.get("OCI_BUCKET_NAME")
        self.namespace = os.environ.get("OCI_NAMESPACE")
        self.subfolder_path = "cityhall/public_works"
        self.items = []  # Lista para armazenar os itens coletados

    def process_item(self, item, spider):
        self.items.append(dict(item))  # Armazena o item coletado
        return item

    def close_spider(self, spider):
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
                content_type="application/json"
            )
            print(f"Arquivo '{file_name}' enviado para o bucket '{self.bucket_name}'.")
        except oci.exceptions.ServiceError as error:
            print(f"Erro ao enviar o arquivo {file_name} para o OCI Bucket: {error}")

    def __initialize_oci_client(self):
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
