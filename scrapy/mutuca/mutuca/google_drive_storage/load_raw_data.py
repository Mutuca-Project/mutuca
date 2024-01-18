import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

"""
Este módulo insere os arquivos PDF raspados no diretório:
CARUARU_CITY_CONCIL/PARLAMENTARY_ALLOANCE/FUEL/PDF
"""

# Lista com o nome dos arquivos a serem enviados
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__name__))))
temp_dir = os.path.join(root_dir, "parlamentary_allowance")
file_paths = [os.path.join(temp_dir, file_name) for file_name in os.listdir(temp_dir)]

# Obtém as credenciais da conta de serviço do Google Cloud
credentials = service_account.Credentials.from_service_account_file(
    "credentials.json",
    # Define a lista de escopos de permissão: https://developers.google.com/drive/api/guides/api-specific-auth?hl=pt-br
    scopes=[
        "https://www.googleapis.com/auth/drive.file",
    ],
)

# Constrói um recurso para interagir com a API
service = build("drive", "v3", credentials=credentials)

# Define os metadados para cada arquivo e realiza o upload
for file_name in file_paths:
    file_metadata = {
        "name": os.path.basename(file_name),
        # Id do diretório onde o arquivo será carregado
        "parents": ["1Rf2FWRUk1acuZUcHAkpjkTif54QRjZhC"],
        # A chave "mimeType" é usada para especificar o tipo MIME do arquivo que está sendo criado ou atualizado no Google Drive.
        # https://developers.google.com/drive/api/guides/mime-types?hl=pt-br
        "mimeType": "application/pdf",
    }

    # mimeType: https://developers.google.com/drive/api/guides/ref-export-formats?hl=pt-br
    media = MediaFileUpload(file_name, mimetype="application/pdf")

    # Faz o upload do arquivo dentro do novo diretório especificado em `parents`
    created_file = (
        service.files().create(body=file_metadata, media_body=media).execute()
    )

    # Imprime o id do documento importado no Google Drive
    print(f'File with ID: "{created_file.get("id")}" has been uploaded.')
