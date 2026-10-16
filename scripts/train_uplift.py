import pandas as pd
import numpy as np
import clickhouse_connect
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklift.models import TwoModels
from sklift.metrics import uplift_auc_score
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import json
import os

CH_HOST = 'clickhouse'
CH_PORT = 8123


def qini_curve(y_true, uplift, treatment):
    """Кастомный Qini curve (sklift 0.5.1 сломан)."""
    order = np.argsort(-uplift)
    y_true = np.asarray(y_true)[order]
    treatment = np.asarray(treatment)[order]

    n = len(y_true)
    cum_treated = np.cumsum(y_true * treatment)
    cum_control = np.cumsum(y_true * (1 - treatment))
    n_treated = np.cumsum(treatment)
    n_control = np.cumsum(1 - treatment)

    # Qini: treated - control * (n_treated / n_control)
    ratio = n_treated / np.maximum(n_control, 1)
    qini = cum_treated - cum_control * ratio
    qini = np.concatenate([[0], qini])

    x = np.arange(n + 1) / n
    return x, qini


def uplift_at_k(y_true, uplift, treatment, k=0.1):
    n = int(len(uplift) * k)
    idx = np.argsort(-uplift)[:n]
    treated = y_true[idx][treatment[idx] == 1].mean()
    control = y_true[idx][treatment[idx] == 0].mean()
    return treated - control


def main():
    print("Чтение данных из ClickHouse...")
    ch = clickhouse_connect.get_client(
        host=CH_HOST, port=CH_PORT,
        username='admin', password='admin123',
    )
    df = ch.query_df('SELECT * FROM uplift_users')
    print(f"Прочитано {len(df)} строк")

    features = ['age', 'income', 'loyalty_days', 'prev_purchases', 'segment']
    X = df[features]
    y = df['purchase']
    treatment = df['treatment']

    X_train, X_test, y_train, y_test, t_train, t_test = train_test_split(
        X, y, treatment, test_size=0.3, random_state=42, stratify=treatment
    )
    print(f"Train: {len(X_train)}, Test: {len(X_test)}")

    print("\nОбучение TwoModels (RandomForest)...")
    tm = TwoModels(
        estimator_trmnt=RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1),
        estimator_ctrl=RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1),
        method='vanilla',
    )
    tm = tm.fit(X_train, y_train, t_train)

    uplift_pred = tm.predict(X_test)

    # Метрики
    auuc = uplift_auc_score(y_test, uplift_pred, t_test)
    x_qini, qini_values = qini_curve(y_test.values, uplift_pred, t_test.values)
    
    # Qini baseline — прямая от 0 до qini_values[-1]
    baseline_qini = qini_values[-1] * x_qini
    qini_auc = np.trapz(qini_values - baseline_qini, x_qini) / len(qini_values)

    uplift_10 = uplift_at_k(y_test.values, uplift_pred, t_test.values, 0.1)
    uplift_20 = uplift_at_k(y_test.values, uplift_pred, t_test.values, 0.2)
    uplift_30 = uplift_at_k(y_test.values, uplift_pred, t_test.values, 0.3)
    uplift_50 = uplift_at_k(y_test.values, uplift_pred, t_test.values, 0.5)

    print(f"\n=== МЕТРИКИ ===")
    print(f"AUUC:        {auuc:.4f}")
    print(f"Qini AUC:    {qini_auc:.4f}")
    print(f"Uplift@10%:  {uplift_10:+.4f}")
    print(f"Uplift@20%:  {uplift_20:+.4f}")
    print(f"Uplift@30%:  {uplift_30:+.4f}")
    print(f"Uplift@50%:  {uplift_50:+.4f}")

    # Baseline (случайный таргетинг)
    baseline_uplift = y_test[t_test == 1].mean() - y_test[t_test == 0].mean()
    print(f"\nBaseline (случайный): {baseline_uplift:+.4f}")
    print(f"Улучшение @10%:       {uplift_10 / baseline_uplift:.2f}x")

    # === График Qini-кривой ===
    plt.figure(figsize=(10, 6))
    plt.plot(x_qini, qini_values, label='Uplift model', color='#3b82f6', linewidth=2)
    plt.plot([0, 1], [0, qini_values[-1]], label='Random', color='gray', linestyle='--')
    plt.xlabel('Доля пользователей (отсортировано по uplift)')
    plt.ylabel('Кумулятивный uplift')
    plt.title('Qini Curve: Uplift Model vs Random')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig('/opt/airflow/data/qini_curve.png', dpi=100)
    plt.close()
    print("\nГрафик сохранён: data/qini_curve.png")

    # === Сегментация ===
    test_df = X_test.copy()
    test_df['uplift'] = uplift_pred
    test_df['purchase'] = y_test.values
    test_df['treatment'] = t_test.values
    test_df['segment_true'] = df.loc[X_test.index, 'segment'].values

    # Топ-30% по uplift — целевая группа
    test_df = test_df.sort_values('uplift', ascending=False).reset_index(drop=True)
    n_top30 = int(len(test_df) * 0.3)
    test_df['targeted'] = 0
    test_df.loc[:n_top30, 'targeted'] = 1

    print("\n=== Сегментация ===")
    print(f"Топ-30% (целевые): {n_top30} пользователей")

    # Эффект от таргетинга топ-30%
    targeted_df = test_df[test_df['targeted'] == 1]
    treated = targeted_df[targeted_df['treatment'] == 1]['purchase'].mean()
    control = targeted_df[targeted_df['treatment'] == 0]['purchase'].mean()
    print(f"Uplift в топ-30%: {treated - control:+.4f}")

    # Эффект от таргетинга всех
    treated_all = test_df[test_df['treatment'] == 1]['purchase'].mean()
    control_all = test_df[test_df['treatment'] == 0]['purchase'].mean()
    print(f"Uplift всех:      {treated_all - control_all:+.4f}")

    # === Сохраняем метрики ===
    metrics = {
        'auuc': float(auuc),
        'qini_auc': float(qini_auc),
        'uplift_at_10': float(uplift_10),
        'uplift_at_20': float(uplift_20),
        'uplift_at_30': float(uplift_30),
        'uplift_at_50': float(uplift_50),
        'baseline_uplift': float(baseline_uplift),
        'improvement_at_10': float(uplift_10 / baseline_uplift),
        'train_size': int(len(X_train)),
        'test_size': int(len(X_test)),
    }

    with open('/opt/airflow/data/uplift_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)

    # Сохраняем предсказания
    test_df.to_csv('/opt/airflow/data/uplift_predictions.csv', index=False)

    print("\nМетрики:")
    print(json.dumps(metrics, indent=2))
    print("\nСохранено:")
    print("  - data/uplift_metrics.json")
    print("  - data/uplift_predictions.csv")
    print("  - data/qini_curve.png")


if __name__ == '__main__':
    main()
