from __future__ import print_function
import wielder.util.util as wu

import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly',
          'https://www.googleapis.com/auth/drive.file']


def service_login(conf):
    """Logs in and returns service object."""

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.

    token_key = f'{conf.google_credentials_path}/token.json'
    creds_key = f'{conf.google_credentials_path}/credentials.json'
    if wu.exists(token_key):
        creds = Credentials.from_authorized_user_file(token_key, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_key, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with wu.open(token_key, 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('drive', 'v3', credentials=creds)
        return service

    except HttpError as error:
        print(f'An error occurred: {error}')
