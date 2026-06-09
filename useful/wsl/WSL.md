

# Install WSL
=
1. Open PowerShell as an Administrator.
1. Run the following command to install WSL:
1. powershell
```
wsl --install
```

1. Restart your computer if prompted.
1. Set up your Linux distribution by following the on-screen instructions.

Install Docker
==

1. Download Docker Desktop for Windows from the Docker website.

1. Run the installer and follow the setup instructions.

1. Make sure to configure Docker to use the WSL 2 backend:

1. Open Docker Desktop settings.

1. Go to the "General" tab and enable "Use the WSL 2 based engine."

1. Apply & Restart Docker Desktop.

1. Install Kubernetes On Docker
1. Open Docker Desktop settings.

1. Go to the "Kubernetes" tab.

1. Check "Enable Kubernetes" and click "Apply & Restart."

1. Wait for Kubernetes to start.

Install Sublime
=

1. Download Sublime Text from the Sublime Text website.

1. Run the installer and follow the setup instructions.

1. Point to WSL Directory
1. Open Sublime Text.

1. Go to "Preferences" > "Settings".

1. Add the following lines to your settings file to point to your WSL directory:

```
"folders":
[
    {
        "path": "//wsl$/Ubuntu/home/your_username"
    }
]

```

Install SourceTree
=

1. Download SourceTree from the SourceTree website.

1. Run the installer and follow the setup instructions.

1. Log in with your Atlassian account or create a new one.

1. Connect to your Bitbucket or GitHub account if needed.

1.  Follow the prompts to complete the setup.
