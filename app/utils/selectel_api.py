import requests
import json
from flask import current_app

class SelectelAPI:
    """
    Client for Selectel Cloud (OpenStack) API.
    Handles authentication via Keystone and operations via Nova.
    """
    def __init__(self):
        self.auth_url = current_app.config.get('SELECTEL_AUTH_URL')
        self.username = current_app.config.get('SELECTEL_USERNAME')
        self.password = current_app.config.get('SELECTEL_PASSWORD')
        self.project_id = current_app.config.get('SELECTEL_PROJECT_ID')
        self.domain_name = current_app.config.get('SELECTEL_DOMAIN_NAME', 'Default')
        self.region = current_app.config.get('SELECTEL_REGION', 'ru-1')
        self._token = None

    def _get_token(self):
        """Authenticates and returns a Keystone token."""
        if self._token:
            # TODO: Add token expiration check
            return self._token

        payload = {
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": self.username,
                            "domain": {"name": self.domain_name},
                            "password": self.password
                        }
                    }
                },
                "scope": {
                    "project": {"id": self.project_id}
                }
            }
        }
        
        url = f"{self.auth_url}/auth/tokens"
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        self._token = response.headers.get('X-Subject-Token')
        return self._token

    def _get_nova_url(self):
        """Builds the base URL for Nova (Compute API)."""
        # Usually something like: https://ru-1.api.selvpc.ru/compute/v2.1
        return f"https://{self.region}.api.selvpc.ru/compute/v2.1"

    def _request(self, method, path, **kwargs):
        """Helper for authenticated requests."""
        token = self._get_token()
        url = f"{self._get_nova_url()}/{path}"
        headers = {
            "X-Auth-Token": token,
            "Content-Type": "application/json"
        }
        response = requests.request(method, url, headers=headers, **kwargs)
        if response.status_code != 204: # 204 No Content
            response.raise_for_status()
        return response.json() if response.content else None

    def list_vms(self):
        """Returns a list of all VMs (servers) in the project."""
        return self._request("GET", "servers")

    def get_vm_details(self, server_id):
        """Returns detailed information about a specific VM."""
        return self._request("GET", f"servers/{server_id}")

    def start_vm(self, server_id):
        """Powers on a stopped VM."""
        payload = {"os-start": None}
        return self._request("POST", f"servers/{server_id}/action", json=payload)

    def stop_vm(self, server_id):
        """Powers off a VM."""
        payload = {"os-stop": None}
        return self._request("POST", f"servers/{server_id}/action", json=payload)

    def suspend_vm(self, server_id):
        """Suspends a VM (saves state to disk)."""
        payload = {"suspend": None}
        return self._request("POST", f"servers/{server_id}/action", json=payload)

    def resume_vm(self, server_id):
        """Resumes a suspended VM."""
        payload = {"resume": None}
        return self._request("POST", f"servers/{server_id}/action", json=payload)

    def reboot_vm(self, server_id, hard=False):
        """Reboots a VM."""
        payload = {"reboot": {"type": "HARD" if hard else "SOFT"}}
        return self._request("POST", f"servers/{server_id}/action", json=payload)
