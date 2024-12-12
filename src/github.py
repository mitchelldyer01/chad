import requests
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class GitHubClient:
    def __init__(self, token: str, owner: str, repo: str):
        self.base_url = "https://api.github.com"
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.owner = owner
        self.repo = repo

    def get_pull_requests(self, state: str = "open") -> List[Dict]:
        """Fetch pull requests from GitHub."""
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/pulls"
        params = {'state': state}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch pull requests: {e}")
            return []

    def submit_review_comment(self, pr_number: int, comment: str) -> bool:
        """Submit a review comment on a pull request."""
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/issues/{pr_number}/comments"
        data = {'body': comment}
        
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to submit review comment: {e}")
            return False

    def get_pr_files(self, pr_number: int) -> List[Dict]:
        """Get list of files changed in a pull request."""
        url = f"{self.base_url}/repos/{self.owner}/{self.repo}/pulls/{pr_number}/files"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch PR files: {e}")
            return []
