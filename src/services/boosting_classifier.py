# services/boosting_classifier.py

import pickle
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report


class BoostingFraudClassifier:
    """
    Обёртка над предобученной градиентной бустинг-моделью (XGBoost, LightGBM и т.п.).
    """

    FEATURE_COLS = [
        "cex_listings", "large_dumps_detected", "is_verified",
        "has_mint", "has_blacklist", "has_setfee", "has_withdraw",
        "has_unlock", "has_pause", "has_changefee", "has_owner"
    ]

    def __init__(self, model_path: str):
        with open(model_path, "rb") as f:
            self.model = pickle.load(f)

    def _prepare(self, X: pd.DataFrame) -> pd.DataFrame:
        df = X.copy()
        # boolean → int, гарантируем все нужные столбцы
        for col in self.FEATURE_COLS:
            df[col] = df.get(col, False).astype(int)
        return df[self.FEATURE_COLS]

    def predict(self, X: pd.DataFrame) -> pd.Series:
        Xp = self._prepare(X)
        return self.model.predict(Xp)

    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        Xp = self._prepare(X)
        probs = self.model.predict_proba(Xp)
        return pd.DataFrame(
            probs,
            columns=[f"prob_class_{i}" for i in range(self.model.n_classes_)]
        )

    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict:
        preds = self.predict(X)
        return {
            "accuracy": accuracy_score(y, preds),
            "classification_report": classification_report(y, preds, output_dict=True)
        }
