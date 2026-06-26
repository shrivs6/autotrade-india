"""
Model registry — saves and loads versioned XGBoost models.
Registry metadata is stored in PostgreSQL (survives Railway deploys).
The .joblib model file is stored on the filesystem; falls back to the
git-committed baseline (model_v1_initial.joblib) if the file was wiped by a deploy.
Only promotes a new model to production if its AUC beats the current one.
"""
import os
import joblib
from datetime import datetime, timezone
from xgboost import XGBClassifier
from backend.database.connection import SessionLocal
from backend.database.models import MlModelRegistry
from backend.utils.logger import get_logger

logger = get_logger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
BASELINE_FILENAME = "model_v1_initial.joblib"


def save_model(model: XGBClassifier, version: str, auc: float, metadata: dict = None) -> str:
    """
    Saves a model to disk and records metadata in PostgreSQL.
    Returns the file path.
    """
    os.makedirs(MODELS_DIR, exist_ok=True)
    filename = f"model_{version}.joblib"
    path = os.path.join(MODELS_DIR, filename)
    joblib.dump(model, path)

    db = SessionLocal()
    try:
        existing = db.query(MlModelRegistry).filter(MlModelRegistry.version == version).first()
        if existing:
            existing.filename = filename
            existing.auc = auc
            existing.trained_at = datetime.now(timezone.utc)
            existing.metadata_json = metadata or {}
        else:
            db.add(MlModelRegistry(
                version=version,
                filename=filename,
                auc=auc,
                trained_at=datetime.now(timezone.utc),
                is_production=False,
                metadata_json=metadata or {},
            ))
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save model metadata to DB: {e}")
        db.rollback()
    finally:
        db.close()

    logger.info(f"Model saved: version={version}, AUC={auc:.4f}, path={path}")
    return path


def promote_if_better(version: str) -> bool:
    """
    Promotes version to production only if its AUC > current production AUC.
    Returns True if promoted, False if not.
    """
    db = SessionLocal()
    try:
        candidate = db.query(MlModelRegistry).filter(MlModelRegistry.version == version).first()
        if not candidate:
            logger.error(f"Version {version} not found in DB registry")
            return False

        current_prod = (
            db.query(MlModelRegistry)
            .filter(MlModelRegistry.is_production == True)
            .order_by(MlModelRegistry.trained_at.desc())
            .first()
        )

        if current_prod is None or candidate.auc > current_prod.auc:
            if current_prod:
                current_prod.is_production = False
            candidate.is_production = True
            db.commit()
            logger.info(f"Model promoted to production: {version} (AUC={candidate.auc:.4f})")
            return True
        else:
            logger.info(
                f"Model NOT promoted: {version} AUC={candidate.auc:.4f} <= "
                f"production AUC={current_prod.auc:.4f}"
            )
            return False
    except Exception as e:
        logger.error(f"promote_if_better failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def load_production_model() -> XGBClassifier | None:
    """
    Loads the current production model.
    Queries PostgreSQL for the production version, then loads the .joblib file.
    Falls back to the git-committed baseline if the file was wiped by a Railway deploy.
    Returns None if nothing is loadable.
    """
    db = SessionLocal()
    try:
        prod = (
            db.query(MlModelRegistry)
            .filter(MlModelRegistry.is_production == True)
            .order_by(MlModelRegistry.trained_at.desc())
            .first()
        )
    except Exception as e:
        logger.error(f"Failed to query model registry: {e}")
        prod = None
    finally:
        db.close()

    if prod:
        path = os.path.join(MODELS_DIR, prod.filename)
        if os.path.exists(path):
            model = joblib.load(path)
            logger.info(f"Production model loaded: {prod.version} AUC={prod.auc:.4f}, trained={prod.trained_at.strftime('%Y-%m-%d')}")
            return model
        else:
            logger.warning(
                f"Production model file missing after deploy: {prod.filename} "
                f"(AUC={prod.auc:.4f}) — falling back to baseline until tonight's retrain"
            )

    # Fallback: load the git-committed baseline (always present after a fresh deploy)
    baseline_path = os.path.join(MODELS_DIR, BASELINE_FILENAME)
    if os.path.exists(baseline_path):
        logger.warning(f"Loading baseline model ({BASELINE_FILENAME}, AUC≈0.50) — nightly retrain will promote a better model tonight")
        return joblib.load(baseline_path)

    logger.error("No model available — neither production nor baseline found")
    return None


def get_production_version() -> str | None:
    db = SessionLocal()
    try:
        prod = db.query(MlModelRegistry).filter(MlModelRegistry.is_production == True).first()
        return prod.version if prod else None
    except Exception:
        return None
    finally:
        db.close()


def get_production_auc() -> float | None:
    db = SessionLocal()
    try:
        prod = db.query(MlModelRegistry).filter(MlModelRegistry.is_production == True).first()
        return prod.auc if prod else None
    except Exception:
        return None
    finally:
        db.close()
