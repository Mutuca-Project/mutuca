# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
import os

import requests
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from scrapy.pipelines.files import BytesIO, FilesPipeline

load_dotenv()


class GoogleDriveLoadPDF(FilesPipeline):
    """
    Pipeline para download dos arquivos PDF referentes à Conta de Alimentação
    e combustível da Câmara de Vereadores de Caruaru utilizando asURLs
    fornecidas em itens do Scrapy e carregá-los diretamente para o Google Drive.

    Esta classe herda de FilesPipeline do Scrapy e substitui os métodos
    process_item, download_file e upload_to_google_drive para personalizar
    o comportamento de download e upload de arquivos.

    Args:
        FilesPipeline: Classe base para pipelines de arquivos do Scrapy.

    Attributes:
        service: Serviço do Google Drive usado para fazer upload de arquivos.
    """

    def __init__(self, *args, **kwargs):
        self.service = self.__get_google_credentials()
        super().__init__(*args, **kwargs)

    def process_item(self, item, spider):
        if self.FILES_URLS_FIELD in item:
            for file_url in item[self.FILES_URLS_FIELD]:
                download_file_content = self.download_file(file_url)
                self.upload_to_google_drive(item, download_file_content)

        return item

    def download_file(self, file_url):
        try:
            response = requests.get(file_url)
            if response.status_code == 200:
                return response.content
            else:
                print(
                    f"Failed to download file from {file_url} - Status Code: {response.status_code} "
                )

        except Exception as error:
            print(f"Error downloading file from {file_url}: {error}")

        return None

    def upload_to_google_drive(self, item, file_content):
        file_name = item["file_id"]
        try:
            media = MediaIoBaseUpload(BytesIO(file_content), mimetype="application/pdf")

            file_metadata = {
                "name": file_name,
                "parents": [os.environ.get("GOOGLE_DRIVE_DIR")],
                "mimeType": "application/pdf",
            }

            created_file = (
                self.service.files()
                .create(body=file_metadata, media_body=media)
                .execute()
            )

            print(f'File with ID: "{created_file.get("id")}" has been uploaded.')

        except HttpError as error:
            print(f"An error occured: {error}")

    def __get_google_credentials(self):
        credentials = service_account.Credentials.from_service_account_file(
            os.environ.get("GOOGLE_CREDENTIALS_PATH"),
            scopes=[
                "https://www.googleapis.com/auth/drive.file",
            ],
        )

        service = build("drive", "v3", credentials=credentials)

        return service


# class ParliamentaryAllowancePipeline(FilesPipeline):
#     def file_path(self, request, response=None, info=None, *, item=None):
#         return "pdf" + PurePosixPath(urlparse(request.url).path).name
