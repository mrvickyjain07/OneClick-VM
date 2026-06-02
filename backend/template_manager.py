import json
from . import config
from .logger import get_logger

logger = get_logger("TemplateManager")

class TemplateManager:
    def __init__(self):
        self.templates = {}

    def load_templates(self):
        """Loads all JSON templates from the templates directory."""
        config.ensure_directories()
        if not config.TEMPLATE_DIR.exists():
            logger.warning(f"Template directory not found: {config.TEMPLATE_DIR}")
            return

        for file_path in config.TEMPLATE_DIR.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if self._validate_template(data):
                        self.templates[data["os_id"]] = data
                        logger.info(f"Loaded template: {data['os_id']}")
                    else:
                        logger.error(f"Invalid template format: {file_path.name}")
            except Exception as e:
                logger.error(f"Failed to load template {file_path.name}: {e}")

    def _validate_template(self, data):
        required_fields = [
            "os_id", "os_name", "version", "iso_url", 
            "ram_mb", "cpu", "disk_gb", "vm_name_prefix"
        ]
        missing = [field for field in required_fields if field not in data]
        if missing:
            logger.error(f"Missing fields in template: {missing}")
            return False
        return True

    def list_templates(self):
        """Returns a list of loaded templates."""
        return list(self.templates.values())

    def get_template(self, os_id):
        """Returns a specific template by os_id."""
        return self.templates.get(os_id)
