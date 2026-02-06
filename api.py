from dotenv import load_dotenv

load_dotenv("conf/.env")

from app.api.app import create_app
from app.core.config import load_config
from app.core.config_checker import check_config


app = create_app()

if __name__ == "__main__":
    config = load_config()
    check_config()
    app.run(host="0.0.0.0", port=config.server_port)
