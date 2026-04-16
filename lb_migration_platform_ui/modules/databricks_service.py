import requests
import base64
import os
import streamlit as st


# ─────────────────────────────────────────────────────────────
# CREDENTIAL RESOLUTION (MERGED HERE)
# ─────────────────────────────────────────────────────────────
def get_databricks_credentials():
    """Single source of truth for Databricks auth"""

    # 1. From Streamlit session (Settings tab)
    host = st.session_state.get("sb_db_host", "").strip()
    token = st.session_state.get("sb_db_token", "").strip()

    if host and token:
        return host, token

    # 2. From environment (Databricks Apps / system env)
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")

    if host and token:
        return host, token

    # 3. CLI profile (~/.databrickscfg)
    profile = st.session_state.get("sb_db_profile") or os.environ.get("DATABRICKS_CONFIG_PROFILE")

    if profile:
        import configparser
        cfg_path = os.path.expanduser("~/.databrickscfg")

        if os.path.exists(cfg_path):
            config = configparser.ConfigParser()
            config.read(cfg_path)

            if profile in config:
                host = config[profile].get("host")
                token = config[profile].get("token")

                if host and token:
                    return host, token

    return None, None


# ─────────────────────────────────────────────────────────────
# CLIENT
# ─────────────────────────────────────────────────────────────
class DatabricksClient:

    def __init__(self, workspace_url, pat_token):
        self.workspace_url = workspace_url.rstrip('/')
        self.pat_token = pat_token
        self.headers = {
            'Authorization': f'Bearer {pat_token}',
            'Content-Type': 'application/json'
        }

    @classmethod
    def from_app_context(cls):
        """Create client using unified credential logic"""
        host, token = get_databricks_credentials()

        if not host or not token:
            raise ValueError(
                "Databricks credentials not configured.\n"
                "Go to Settings and provide Host + Token OR configure CLI profile."
            )

        return cls(host, token)

    # ─────────────────────────────────────────────────────────
    # WORKSPACE APIs
    # ─────────────────────────────────────────────────────────
    def list_workspace_items(self, path='/'):
        try:
            url = f"{self.workspace_url}/api/2.0/workspace/list"
            response = requests.get(
                url,
                headers=self.headers,
                json={'path': path}
            )
            response.raise_for_status()
            return response.json().get('objects', [])
        except Exception as e:
            return {'error': str(e)}

    def get_file_content(self, path):
        try:
            url = f"{self.workspace_url}/api/2.0/workspace/export"
            response = requests.get(
                url,
                headers=self.headers,
                json={'path': path, 'format': 'SOURCE'}
            )
            response.raise_for_status()
            content = response.json().get('content', '')

            decoded_content = base64.b64decode(content).decode('utf-8')
            return decoded_content

        except Exception as e:
            return {'error': str(e)}

    def create_folder(self, path):
        try:
            url = f"{self.workspace_url}/api/2.0/workspace/mkdirs"
            response = requests.post(
                url,
                headers=self.headers,
                json={'path': path}
            )
            response.raise_for_status()
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    def write_file(self, path, content, language='PYTHON', overwrite=True):
        try:
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

            url = f"{self.workspace_url}/api/2.0/workspace/import"
            response = requests.post(
                url,
                headers=self.headers,
                json={
                    'path': path,
                    'content': encoded_content,
                    'language': language,
                    'format': 'SOURCE',
                    'overwrite': overwrite
                }
            )
            response.raise_for_status()
            return {'success': True, 'path': path}
        except Exception as e:
            return {'error': str(e)}