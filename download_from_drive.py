import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.auth
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import io
import time
import os
import glob
import tqdm


SCOPES = ["https://www.googleapis.com/auth/drive"]


def download_files_in_folder(folder_id, output, downloaded_files, delete_on_drive=False):
    try:
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        try:
            if os.path.exists("/home/rene1337/RSCPH/landsat_tree_analysis/token.json"):
                creds = Credentials.from_authorized_user_file("/home/rene1337/RSCPH/landsat_tree_analysis/token.json", SCOPES)
            # If there are no (valid) credentials available, let the user log in.
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        "/home/rene1337/RSCPH/landsat_tree_analysis/creds.json", SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                    # Save the credentials for the next run
                with open("/home/rene1337/RSCPH/landsat_tree_analysis/token.json", "w") as token:
                    token.write(creds.to_json())
        except Exception as error:
            print(f"An error occurred: {error}")
            if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                "/home/rene1337/RSCPH/landsat_tree_analysis/creds.json", SCOPES
            )
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open("/home/rene1337/RSCPH/landsat_tree_analysis/token.json", "w") as token:
                token.write(creds.to_json())

        drive_service = build('drive', 'v3', credentials=creds)

        folderId = folder_id

        items = []
        pageToken = ""
        while pageToken is not None:
            response = drive_service.files().list(q="'" + folderId + "' in parents", pageSize=1000, pageToken=pageToken,
                                                fields="nextPageToken, files(id, name)").execute()
            items.extend(response.get('files', []))
            pageToken = response.get('nextPageToken')

        for file in items:
            
            real_file_id = file.get("id")
            real_file_name = file.get("name")
            split = real_file_name.split("_")
            
            if file.get("real_file_name") in downloaded_files:
                    print(f"Skipping file: {file.get('name')}")
                    continue
        
            grid_id = f"{split[1]}_{split[2]}"
            os.makedirs(f"{output}/{grid_id}", exist_ok=True)
            date = f"{split[3]}-{split[4]}-{split[5]}"
            os.makedirs(f"{output}/{grid_id}/{date}", exist_ok=True)
        
            output_fp = f"{output}/{grid_id}/{date}/{real_file_name}"
            
            request = drive_service.files().get_media(fileId=real_file_id)
            ### Saves all files under outputFolder
            fh = io.FileIO(output_fp, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                #print(f"Download {int(status.progress() * 100)}.")
            print(f'{real_file_name} downloaded completely.')
                
            if delete_on_drive:
                print(f"Deleting file: {real_file_name}")
                creds = None
                # The file token.json stores the user's access and refresh tokens, and is
                # created automatically when the authorization flow completes for the first
                # time.
                if os.path.exists("/home/rene1337/RSCPH/landsat_tree_analysis/token.json"):
                    creds = Credentials.from_authorized_user_file("/home/rene1337/RSCPH/landsat_tree_analysis/token.json", SCOPES)
                # If there are no (valid) credentials available, let the user log in.
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    else:
                        flow = InstalledAppFlow.from_client_secrets_file(
                        "/home/rene1337/RSCPH/landsat_tree_analysis/creds.json", SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                    # Save the credentials for the next run
                    with open("/home/rene1337/RSCPH/landsat_tree_analysis/token.json", "w") as token:
                        token.write(creds.to_json())

                # create drive api client
                service = build("drive", "v3", credentials=creds)

                response = service.files().delete(fileId=real_file_id).execute()
                
    except Exception as error:
        print(f"An error occurred: {error}")
        
        
def search_file():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("/home/rene1337/RSCPH/landsat_tree_analysis/token.json"):
        creds = Credentials.from_authorized_user_file("/home/rene1337/RSCPH/landsat_tree_analysis/token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
            "/home/rene1337/RSCPH/landsat_tree_analysis/creds.json", SCOPES
        )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("/home/rene1337/RSCPH/landsat_tree_analysis/token.json", "w") as token:
            token.write(creds.to_json())

    try:
        # create drive api client
        service = build("drive", "v3", credentials=creds)
        files = []
        page_token = None
        while True:
        # pylint: disable=maybe-no-member
            response = (
            service.files()
            .list(
                q=search_query,
                spaces="drive",
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
            )
            .execute()
                        )
            #for file in tqdm.tqdm(response.get("files", [])):
            # Process change
            #print(f'Found file: {file.get("name")}, {file.get("id")}')
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken", None)
            if page_token is None:
                break

    except Exception as error:
        print(f"An error occurred: {error}")
        files = None

    return files

        
def search_folder(search_query):
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  if os.path.exists("/home/rene1337/RSCPH/landsat_tree_analysis/token.json"):
    creds = Credentials.from_authorized_user_file("/home/rene1337/RSCPH/landsat_tree_analysis/token.json", SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          "/home/rene1337/RSCPH/landsat_tree_analysis/creds.json", SCOPES
      )
      creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("/home/rene1337/RSCPH/landsat_tree_analysis/token.json", "w") as token:
      token.write(creds.to_json())

  try:
    # create drive api client
    service = build("drive", "v3", credentials=creds)
    files = []
    page_token = None
    while True:
      # pylint: disable=maybe-no-member
      response = (
          service.files()
          .list(
              q=search_query,
              spaces="drive",
              fields="nextPageToken, files(id, name)",
              pageToken=page_token,
          )
          .execute()
      )
      #for file in tqdm.tqdm(response.get("files", [])):
        # Process change
        #print(f'Found file: {file.get("name")}, {file.get("id")}')
      files.extend(response.get("files", []))
      page_token = response.get("nextPageToken", None)
      if page_token is None:
        break

  except Exception as error:
    print(f"An error occurred: {error}")
    files = None

  return files


if __name__ == "__main__":
    qnap_dir = "/media/rene1337/27e47104-4197-4926-a3d0-101c850014fe"
    out_dir = f"{qnap_dir}/global_drylands_landsat_download"
    
    os.makedirs(out_dir, exist_ok=True)
    
    """continuously downloads if folders contain less than 50 files. 
    So when exporting to drive it is nessassary to save no more than 
    50 files to any one folder.
    
    ***REQUIRED: credentials.json created and downloaded from google cloud projects:
    https://console.cloud.google.com/apis/credentials and add OAuth2.0 Client ID
    """
    
    folders_len = 1
    
    while folders_len > 0:
        
        # Search query
        # https://developers.google.com/drive/api/guides/search-files for more queries
        search_query = "name contains 'ls789' and mimeType = 'application/vnd.google-apps.folder'"
        
        # Search for folders on google drive
        folders = search_folder(search_query=search_query)
        
        # Search individual files
        #files = search_file()
        
        folders_len = len(folders)
        print(f"Found {folders_len} files")

        downloaded_files = glob.glob(f"{out_dir}/**/*.tif", recursive=True)
        downloaded_files = [os.path.basename(file) for file in downloaded_files]
        
        count = 0
        for folder in tqdm.tqdm(folders):
            if folder.get("name") in downloaded_files:
                print(f"Skipping file: {folder.get('name')}")
                continue
            count += 1
            #print(count)
            
            download_files_in_folder(folder_id=folder.get("id"), 
                                     output=out_dir, 
                                     downloaded_files=downloaded_files, 
                                     delete_on_drive=True)
            
            # if you want to download a file indivisually.
            #download_file(file, out_dir, delete_on_drive=True)

        print("Sleeping for 1 hour")
        time.sleep(60*60*1)