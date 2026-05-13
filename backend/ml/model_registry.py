"""
Model registry — saves and loads versioned XGBoost models.
Only promotes a new model to production if its AUC beats the current one.
"""
import os
import json
import joblib
from datetime import datetime
from xgboost import XGBClassifier
from backend.utils.logger import get_logger

logger = get_logger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
REGISTRY_FILE = os.path.join(MODELS_DIR, "registry.json")
PRODUCTION_KEY = "production"


def _load_registry() -> dict:
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    return {}


def _save_registry(registry: dict):
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)


def save_model(model: XGBClassifier, version: str, auc: float, metadata: dict = None) -> str:
    """
    Saves a model to disk with version tag.
    Returns the file path.
    """
    os.makedirs(MODELS_DIR, exist_ok=True)
    path = os.path.join(MODELS_DIR, f"model_{version}.joblib")
    joblib.dump(model, path)

    registry = _load_registry()
    registry[version] = {
        "path": path,
        "auc": auc,
        "trained_at": datetime.now().isoformat(),
        "metadata": metadata or {},
    }
    _save_registry(registry)

    logger.info(f"Model saved: version={version}, AUC={auc:.4f}, path={path}")
    return path


def promote_if_better(version: str) -> bool:
    """
    Promotes version to production only if its AUC > current production AUC.
    Returns True if promoted, False if not.
    """
    registry = _load_registry()

    if version not in registry:
        logger.error(f"Version {version} not found in registry")
        return False

    new_auc = registry[version]["auc"]
    current = registry.get(PRODUCTION_KEY)

    if current is None or new_auc > current.get("auc", 0):
        registry[PRODUCTION_KEY] = {**registry[version], "promoted_from": version}
        _save_registry(registry)
        logger.info(f"Model promoted to production: {version} (AUC={new_auc:.4f})")
        return True
    else:
        logger.info(
            f"Model NOT promoted: {version} AUC={new_auc:.4f} <= "
            f"production AUC={current['auc']:.4f}"
        )
        return False


def load_production_model() -> XGBClassifier | None:
    """Loads the current production model. Returns None if none exists."""
    registry = _load_registry()
    prod = registry.get(PRODUCTION_KEY)

    if not prod:
        logger.warning("No production model found")
        return None

    path = prod["path"]
    # Fall back to MODELS_DIR-relative filename if absolute path doesn't exist (e.g. on Railway)
    if not os.path.exists(path):
        filename = os.path.basename(path)
        path = os.path.join(MODELS_DIR, filename)
    if not os.path.exists(path):
        logger.error(f"Production model file not found: {path}")
        return None

    model = joblib.load(path)
    logger.info(f"Production model loaded: AUC={prod['auc']:.4f}, trained={prod['trained_at'][:10]}")
    return model


def get_production_version() -> str | None:
    """Returns version string of the current production model."""
    registry = _load_registry()
    prod = registry.get(PRODUCTION_KEY)
    return prod.get("promoted_from") if prod else None


def get_production_auc() -> float | None:
    """Returns AUC of the current production model."""
    registry = _load_registry()
    prod = registry.get(PRODUCTION_KEY)
    return prod.get("auc") if prod else None
