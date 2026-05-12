"""
One-time script to train the initial v1 XGBoost model.

Run after Phase 2 backfill is complete:
    cd "Trading Simulater"
    source venv/bin/activate
    python -m backend.scripts.train_initial_model
"""
from backend.ml.dataset_builder import build_dataset
from backend.ml.model_trainer import train_model, walk_forward_validate
from backend.ml.model_evaluator import evaluate_thresholds, get_feature_importance
from backend.ml.model_registry import save_model, promote_if_better

print("Step 1/4: Building labeled dataset...")
df = build_dataset()
print(f"  Dataset: {len(df):,} rows, win rate: {df['label'].mean():.1%}")

print("\nStep 2/4: Walk-forward validation...")
wf = walk_forward_validate(df, n_splits=4)
print(f"  Avg AUC: {wf['avg_auc']:.4f}")

print("\nStep 3/4: Training on full dataset...")
model, eval_auc = train_model(df)

print("\nStep 4/4: Evaluating thresholds...")
threshold_results = evaluate_thresholds(model, df)
print(threshold_results.to_string(index=False))

print("\nFeature importance:")
get_feature_importance(model, top_n=10)

print("\nSaving model...")
save_model(model, version="v1_initial", auc=wf["avg_auc"], metadata={"walk_forward": wf})
promote_if_better("v1_initial")

print("\nDone! Model v1_initial saved and set as production.")
