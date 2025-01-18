import os
import requests
from dotenv import load_dotenv
from io import BytesIO
from scrapy.pipelines.files import FilesPipeline
import oci

load_dotenv()

class OCIUploadPDFPipeline(FilesPipeline):

    def __init__(self, *args, **kargs):
        self.oci_client = self.__get_oci_client()
        self.bucket_name = os.environ.get("OCI_BUCKET_NAME")
        self.namespace = os.environ.get("OCI_NAMESPACE")
        self.subfolder_path = "municipal-council/parliamentary-allowance"
        super().__init__(*args, **kargs)
    
    def process_item(self, item, spider):
        if self.FILES_URLS_FIELD in item:
            for file_url in item[self.FILES_URLS_FIELD]:
                download_file_content = self.download_file(file_url)
                if download_file_content:
                    self.upload_to_oci_bucket(item, download_file_content)
        
        return item

    def download_file(self, file_url):
        try:
            response = requests.get(file_url)
            if response.status_code == 200:
                return response.content
            else:
                print(f"Failed to download file from {file_url} - Status Code: {response.status_code}")

        except Exception as error: 
            print(f"Error downloading file from {file_url}: {error}")

        return None

    def upload_to_oci_bucket(self, item, file_content):
        file_name = item.get("file_id", "default_file_name")
        object_name = f"{self.subfolder_path}/{file_name}"

        try:
            self.oci_client.put_object(
                    namespace_name=self.namespace,
                    bucket_name=self.bucket_name,
                    object_name=object_name,
                    put_object_body=BytesIO(file_content),
                    content_type="application/pdf"
            )
            print(f"File '{file_name}' has been uploaded to bucket '{self.bucket_name}'.")
        except oci.exceptions.ServiceError as error:
            print(f"Error uploading file {file_name} to OCI Bucket: {error}")

    def __get_oci_client(self):
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
            print(f"Error initializing OCI client: {error}")
            raise


