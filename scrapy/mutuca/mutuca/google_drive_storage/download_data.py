import io
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload


def download_files_from_folder(folder_id, download_dir):
    """Downloads all files from a folder in Google Drive.
    Args:
        folder_id: ID of the folder to download files from.
    Returns : List of downloaded files as IO objects.
    """

    # Obtém as credenciais da conta de serviço do Google Cloud
    credentials = service_account.Credentials.from_service_account_file(
        "credentials.json",
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )

    downloaded_files = []

    try:
        # Cria o drive da api client
        service = build("drive", "v3", credentials=credentials)

        # Lista os aruivos do diretório do google drive
        results = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents",
                fields="files(id, name)",
            )
            .execute()
        )

        files = results.get("files", [])

        # Cria o diretório de cada arquivo se não existir
        os.makedirs(download_dir, exist_ok=True)

        for file in files:
            file_id = file["id"]
            file_name = file["name"]
            print(f"Downloading file: {file_name} (ID: {file_id})")

            # download de cada arquivo
            request = service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)
            done = False

            while done is False:
                status, done = downloader.next_chunk()
                print(f"Download {int(status.progress() * 100)}.")

            file_path = os.path.join(download_dir, file_name)
            with open(file_path, "wb") as f:
                f.write(file_content.getvalue())

            downloaded_files.append(file_path)

    except HttpError as error:
        print(f"An error occurred: {error}")

    return downloaded_files


if __name__ == "__main__":

    root_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__name__)))
    )
    download_dir = os.path.join(root_dir, "download_dir")

    folder_id = "1Rf2FWRUk1acuZUcHAkpjkTif54QRjZhC"

    downloaded_files = download_files_from_folder(folder_id, download_dir)

    # Lista dos arquivos baixados
    for file in downloaded_files:
        print(f"File downloaded successfully: {os.path.basename(file)}")
