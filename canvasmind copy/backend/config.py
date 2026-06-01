import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_GPTTEXT52",
    "AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1",
]

OPTIONAL_DEFAULTS = {
    "BACKEND_PORT": "8000",
    "WS_PORT": "8001",
    "FRONTEND_PORT": "3000",
    "MAX_ROUNDS": "10",
    "SESSION_TIMEOUT": "300",
    "LOG_LEVEL": "INFO",
    "SESSION_STORAGE_PATH": "./data/sessions",
}


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "****"
    return f"****{key[-4:]}"


def validate_config() -> None:
    missing = [v for v in REQUIRED_VARS if not os.getenv(v, "").strip()]
    if missing:
        print("\n[CanvasMind] FATAL: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nCopy .env.example to .env and fill in all required values.\n")
        sys.exit(1)

    try:
        backend_port = int(os.getenv("BACKEND_PORT", "8000"))
        ws_port = int(os.getenv("WS_PORT", "8001"))
        assert 1024 <= backend_port <= 65535
        assert 1024 <= ws_port <= 65535
    except (ValueError, AssertionError):
        print("[CanvasMind] FATAL: BACKEND_PORT and WS_PORT must be valid port numbers (1024-65535)")
        sys.exit(1)

    try:
        max_rounds = int(os.getenv("MAX_ROUNDS", "10"))
        assert 1 <= max_rounds <= 20
    except (ValueError, AssertionError):
        print("[CanvasMind] FATAL: MAX_ROUNDS must be between 1 and 20")
        sys.exit(1)

    storage_path = Path(os.getenv("SESSION_STORAGE_PATH", "./data/sessions"))
    storage_path.mkdir(parents=True, exist_ok=True)

    _print_banner()


def _print_banner() -> None:
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    print("\n" + "═" * 60)
    print("  CanvasMind — Multi-Agent Creative AI Painting System")
    print("═" * 60)
    print(f"  Azure Endpoint  : {endpoint}")
    print(f"  API Key         : {_mask_key(api_key)}")
    print(f"  API Version     : {os.getenv('AZURE_OPENAI_API_VERSION')}")
    print(f"  Text Deployment : {os.getenv('AZURE_OPENAI_DEPLOYMENT_GPTTEXT52')}")
    print(f"  Image Deployment: {os.getenv('AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1')}")
    print(f"  Backend Port    : {os.getenv('BACKEND_PORT', '8000')}")
    print(f"  Max Rounds      : {os.getenv('MAX_ROUNDS', '10')}")
    print(f"  Storage Path    : {os.getenv('SESSION_STORAGE_PATH', './data/sessions')}")
    print(f"  Log Level       : {os.getenv('LOG_LEVEL', 'INFO')}")
    print("═" * 60 + "\n")


class Settings:
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    deployment_text: str = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPTTEXT52", "")
    deployment_image: str = os.getenv("AZURE_OPENAI_DEPLOYMENT_GPTIMAGE1", "")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
    ws_port: int = int(os.getenv("WS_PORT", "8001"))
    frontend_port: int = int(os.getenv("FRONTEND_PORT", "3000"))
    max_rounds: int = int(os.getenv("MAX_ROUNDS", "10"))
    session_timeout: int = int(os.getenv("SESSION_TIMEOUT", "300"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    session_storage_path: str = os.getenv("SESSION_STORAGE_PATH", "./data/sessions")


settings = Settings()
