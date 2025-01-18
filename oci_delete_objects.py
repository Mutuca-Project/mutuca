import os
from oci.object_storage import ObjectStorageClient
from oci.config import from_file
from dotenv import load_dotenv

load_dotenv()

bucket_name = os.environ.get("OCI_BUCKET_NAME") 
prefix = "municipal-council/parliamentary-allowance/"

config = {
        "user": os.environ.get("OCI_USER"),
        "fingerprint": os.environ.get("OCI_FINGERPRINT"),
        "tenancy": os.environ.get("OCI_TENANCY"),
        "key_file": os.environ.get("OCI_KEY_FILE_PATH"),
        "region": os.environ.get("OCI_REGION"),
}

client = ObjectStorageClient(config)

object_storage_client = ObjectStorageClient(config)
namespace = os.environ.get("OCI_NAMESPACE")

try:
    response = object_storage_client.list_objects(
            namespace_name=namespace,
            bucket_name=bucket_name,
            prefix=prefix,
    )

    objects = response.data.objects

    if objects:
        for obj in objects:
            print(f"Deletando: {obj.name}")
            object_storage_client.delete_object(namespace, bucket_name, obj.name)
        print(f"Todos os arquivos foram deletados do bucket {bucket_name}, prefixo: {prefix}.")
    else:
        print(f"Nenhum arquivo encontrado no bucket {bucket_name}, prefixo: {prefix}.")

except Exception as error:
    print(f"ERROR: {error}")
