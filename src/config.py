import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    REPO_PATH = os.getenv('REPO_PATH')
    REPO_OWNER = os.getenv('REPO_OWNER')
    REPO_NAME = os.getenv('REPO_NAME')
    MODEL_PATH = os.getenv('MODEL_PATH')
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))

    @classmethod
    def validate(cls):
        required_vars = ['GITHUB_TOKEN', 'REPO_PATH', 'REPO_OWNER', 'REPO_NAME', 'MODEL_PATH']
        missing = [var for var in required_vars if not getattr(cls, var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
