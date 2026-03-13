import numpy as np
from sklearn.ensemble import IsolationForest

def calculate_anomaly_score(data_points):
    """
    Analyzes features like (Engagement Rate, Follower Growth, Sentiment Variance).
    Returns a normalized trust penalty.
    """
    # Reshape for sklearn: [Engagement, Growth, ReviewConsistency]
    clf = IsolationForest(contamination=0.2, random_state=42)
    preds = clf.fit_predict(data_points)
    # -1 is anomaly, 1 is normal
    return preds