"""XGBoost model training and inference (T-304).

Trains XGBoost binary classifiers using walk-forward cross-validation
(T-303) with Optuna hyperparameter optimization.  Provides a standalone
prediction function for use by MLV1Generator.

SPEC §5.6: XGBoost with Optuna HPO, walk-forward validation, early
stopping.  AUC-ROC > 0.55 per instrument (log warning if below).
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import optuna
import xgboost as xgb
from sklearn.metrics import roc_auc_score

from src.analysis.feature_engineering import FeatureMatrix
from src.analysis.walk_forward import (
    FoldResult,
    WalkForwardConfig,
    WalkForwardResult,
    collect_results,
    generate_folds,
    validate_no_lookahead,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class XGBoostHyperparameters:
    """Tunable XGBoost hyperparameters."""

    max_depth: int = 6
    learning_rate: float = 0.1
    n_estimators: int = 100
    min_child_weight: float = 1.0
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    gamma: float = 0.0
    reg_alpha: float = 0.0
    reg_lambda: float = 1.0


@dataclass(frozen=True)
class TrainingResult:
    """Aggregated output from walk-forward XGBoost training."""

    walk_forward_result: WalkForwardResult
    production_model_bytes: bytes | None
    production_hyperparameters: XGBoostHyperparameters
    below_auc_threshold: bool
    instrument: str


def train_xgboost(
    *,
    feature_matrix: FeatureMatrix,
    labels: tuple[int, ...],
    walk_forward_config: WalkForwardConfig,
    n_optuna_trials: int = 50,
    early_stopping_rounds: int = 10,
    auc_threshold: float = 0.55,
    random_seed: int = 42,
) -> TrainingResult:
    """Train XGBoost using walk-forward cross-validation with Optuna HPO.

    1. Generate walk-forward folds from the feature matrix.
    2. Optimize hyperparameters on the first fold's training window
       (internal 80/20 split — no test data leakage).
    3. Train each fold with best hyperparameters + early stopping.
    4. Aggregate out-of-fold results.
    5. Train production model on the most recent training window.
    6. Check AUC threshold and log warning if below.
    """
    n_samples = len(feature_matrix.timestamps)
    X = feature_matrix.values
    y = np.array(labels, dtype=np.int32)

    folds = generate_folds(n_samples=n_samples, config=walk_forward_config)
    validate_no_lookahead(folds, embargo_periods=walk_forward_config.embargo_periods)

    # --- Optuna HPO on first fold's training window ---
    first = folds[0]
    hyperparameters = _optimize_hyperparameters(
        X_train=X[first.train_start_idx:first.train_end_idx],
        y_train=y[first.train_start_idx:first.train_end_idx],
        n_trials=n_optuna_trials,
        early_stopping_rounds=early_stopping_rounds,
        random_seed=random_seed,
    )

    # --- Walk-forward: train each fold ---
    fold_results: list[FoldResult] = []
    best_iterations: list[int] = []

    for fold in folds:
        X_train = X[fold.train_start_idx:fold.train_end_idx]
        y_train = y[fold.train_start_idx:fold.train_end_idx]
        X_test = X[fold.test_start_idx:fold.test_end_idx]
        y_test = y[fold.test_start_idx:fold.test_end_idx]
        ts_test = feature_matrix.timestamps[fold.test_start_idx:fold.test_end_idx]

        fold_result, best_iter = _train_fold(
            X_train=X_train,
            y_train=y_train,
            X_test=X_test,
            y_test=y_test,
            timestamps=ts_test,
            fold_number=fold.fold_number,
            hyperparameters=hyperparameters,
            early_stopping_rounds=early_stopping_rounds,
            random_seed=random_seed,
        )
        fold_results.append(fold_result)
        best_iterations.append(best_iter)

    wf_result = collect_results(fold_results=fold_results, config=walk_forward_config)

    # --- Production model on last fold's training window ---
    last = folds[-1]
    prod_n_estimators = max(1, int(np.median(best_iterations)) + 1)
    production_bytes = _train_production_model(
        X_train=X[last.train_start_idx:last.train_end_idx],
        y_train=y[last.train_start_idx:last.train_end_idx],
        hyperparameters=hyperparameters,
        n_estimators=prod_n_estimators,
        random_seed=random_seed,
    )

    below = wf_result.mean_auc_roc < auc_threshold
    if below:
        logger.warning(
            "XGBoost AUC-ROC %.4f below threshold %.2f for %s. "
            "ML component disabled per SPEC §5.6. Falling back to Bayesian-only.",
            wf_result.mean_auc_roc,
            auc_threshold,
            feature_matrix.instrument,
        )

    # SPEC §5.6: disable ML component when AUC below threshold
    final_model_bytes: bytes | None = None if below else production_bytes

    logger.info(
        "XGBoost training complete for %s: mean AUC=%.4f, %d folds, "
        "production model %s",
        feature_matrix.instrument,
        wf_result.mean_auc_roc,
        len(folds),
        f"{len(production_bytes)} bytes" if not below else "DISABLED (below threshold)",
    )

    return TrainingResult(
        walk_forward_result=wf_result,
        production_model_bytes=final_model_bytes,
        production_hyperparameters=hyperparameters,
        below_auc_threshold=below,
        instrument=feature_matrix.instrument,
    )


def predict_xgboost(
    *,
    model_bytes: bytes,
    feature_vector: np.ndarray,
) -> float:
    """Predict event probability from serialized XGBoost model.

    Args:
        model_bytes: Raw XGBoost model bytes (from Booster.save_raw).
        feature_vector: 1-D numpy array of feature values.

    Returns:
        Probability in [0, 1].
    """
    # Ensure bytes (not bytearray) for lru_cache hashability
    key = bytes(model_bytes) if not isinstance(model_bytes, bytes) else model_bytes
    booster = _get_booster(key)
    dmatrix = xgb.DMatrix(feature_vector.reshape(1, -1))
    predictions = booster.predict(dmatrix)
    return float(predictions[0])


@functools.lru_cache(maxsize=8)
def _get_booster(model_bytes: bytes) -> xgb.Booster:
    """Cache deserialized XGBoost boosters to avoid per-call overhead."""
    return _deserialize_model(model_bytes)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _optimize_hyperparameters(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_trials: int,
    early_stopping_rounds: int,
    random_seed: int,
) -> XGBoostHyperparameters:
    """Run Optuna HPO within a training window (80/20 internal split)."""
    n = len(y_train)
    split = int(n * 0.8)
    X_sub, X_val = X_train[:split], X_train[split:]
    y_sub, y_val = y_train[:split], y_train[split:]

    dtrain = xgb.DMatrix(X_sub, label=y_sub)
    dval = xgb.DMatrix(X_val, label=y_val)

    def objective(trial: optuna.Trial) -> float:
        params: dict[str, Any] = {
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 10.0),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "gamma": trial.suggest_float("gamma", 0.0, 5.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 10.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.0, 10.0),
            "seed": random_seed,
            "verbosity": 0,
        }
        booster = xgb.train(
            params, dtrain,
            num_boost_round=300,
            evals=[(dval, "val")],
            early_stopping_rounds=early_stopping_rounds,
            verbose_eval=False,
        )
        preds = booster.predict(dval, iteration_range=(0, booster.best_iteration + 1))
        try:
            return float(roc_auc_score(y_val, preds))
        except ValueError:
            return 0.5

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=random_seed),
    )
    study.optimize(objective, n_trials=n_trials)

    best = study.best_params
    return XGBoostHyperparameters(
        max_depth=best["max_depth"],
        learning_rate=best["learning_rate"],
        n_estimators=300,
        min_child_weight=best["min_child_weight"],
        subsample=best["subsample"],
        colsample_bytree=best["colsample_bytree"],
        gamma=best["gamma"],
        reg_alpha=best["reg_alpha"],
        reg_lambda=best["reg_lambda"],
    )


def _hp_to_xgb_params(hp: XGBoostHyperparameters, seed: int) -> dict[str, Any]:
    """Convert frozen hyperparameters to XGBoost param dict."""
    return {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "max_depth": hp.max_depth,
        "learning_rate": hp.learning_rate,
        "min_child_weight": hp.min_child_weight,
        "subsample": hp.subsample,
        "colsample_bytree": hp.colsample_bytree,
        "gamma": hp.gamma,
        "reg_alpha": hp.reg_alpha,
        "reg_lambda": hp.reg_lambda,
        "seed": seed,
        "verbosity": 0,
    }


def _train_fold(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    timestamps: tuple[datetime, ...],
    fold_number: int,
    hyperparameters: XGBoostHyperparameters,
    early_stopping_rounds: int,
    random_seed: int,
) -> tuple[FoldResult, int]:
    """Train and evaluate on a single walk-forward fold.

    Returns (FoldResult, best_iteration).
    """
    params = _hp_to_xgb_params(hyperparameters, random_seed)

    # 80/20 split within training window for early stopping
    n = len(y_train)
    split = int(n * 0.8)
    X_tr, X_es = X_train[:split], X_train[split:]
    y_tr, y_es = y_train[:split], y_train[split:]

    dtrain = xgb.DMatrix(X_tr, label=y_tr)
    dval = xgb.DMatrix(X_es, label=y_es)
    dtest = xgb.DMatrix(X_test, label=y_test)

    booster = xgb.train(
        params, dtrain,
        num_boost_round=hyperparameters.n_estimators,
        evals=[(dval, "val")],
        early_stopping_rounds=early_stopping_rounds,
        verbose_eval=False,
    )
    best_iter = booster.best_iteration

    test_preds = booster.predict(dtest, iteration_range=(0, best_iter + 1))

    try:
        auc = float(roc_auc_score(y_test, test_preds))
    except ValueError:
        auc = 0.5

    logger.info(
        "Fold %d: AUC-ROC=%.4f, best_iteration=%d",
        fold_number, auc, best_iter,
    )

    return FoldResult(
        fold_number=fold_number,
        metrics={"auc_roc": auc},
        test_predictions=tuple(float(p) for p in test_preds),
        test_labels=tuple(int(label) for label in y_test),
        test_timestamps=timestamps,
    ), best_iter


def _train_production_model(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    hyperparameters: XGBoostHyperparameters,
    n_estimators: int,
    random_seed: int,
) -> bytes:
    """Train production model with fixed round count (no early stopping)."""
    params = _hp_to_xgb_params(hyperparameters, random_seed)
    dtrain = xgb.DMatrix(X_train, label=y_train)
    booster = xgb.train(params, dtrain, num_boost_round=n_estimators, verbose_eval=False)
    return _serialize_model(booster)


def _serialize_model(booster: xgb.Booster) -> bytes:
    """Serialize XGBoost Booster to raw bytes (UBJ format)."""
    return booster.save_raw(raw_format="ubj")  # type: ignore[return-value]


def _deserialize_model(model_bytes: bytes) -> xgb.Booster:
    """Deserialize raw bytes to XGBoost Booster."""
    booster = xgb.Booster()
    booster.load_model(bytearray(model_bytes))
    return booster
