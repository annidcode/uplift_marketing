import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

NUM_USERS = 100_000
TREATMENT_RATIO = 0.5  # 50% в тесте, 50% в контроле

# Параметры эффекта
BASE_CONVERSION = 0.10      # базовая конверсия (без рекламы)
PERSUADABLE_LIFT = 0.15     # эффект для persuadables (+15 п.п.)
SLEEPING_DOG_EFFECT = -0.05 # sleeping dogs (-5 п.п.)

# Сегменты
# 0 - sure things (купили бы и так)
# 1 - persuadables (купили только с рекламой)
# 2 - lost causes (не купили бы вообще)
# 3 - sleeping dogs (реклама вредит)

print(f"Генерация {NUM_USERS} пользователей...")

# Сегменты: 40% sure, 30% persuadables, 25% lost, 5% sleeping dogs
segments = np.random.choice(
    [0, 1, 2, 3],
    size=NUM_USERS,
    p=[0.40, 0.30, 0.25, 0.05]
)

# Реклама: случайно 50/50
treatment = np.random.binomial(1, TREATMENT_RATIO, NUM_USERS)

# Вероятности покупки
p_purchase = np.full(NUM_USERS, BASE_CONVERSION)

# sure things — высокая базовая конверсия
p_purchase[segments == 0] = 0.40

# persuadables — низкая база, но высокий uplift
p_purchase[segments == 1] = 0.05  # базовая 5%

# lost causes — низкая база, нет эффекта
p_purchase[segments == 2] = 0.02

# sleeping dogs — база ок, но реклама вредит
p_purchase[segments == 3] = 0.15

# Применяем эффект рекламы
effect = np.zeros(NUM_USERS)
effect[segments == 1] = PERSUADABLE_LIFT  # +15 п.п. с рекламой
effect[segments == 3] = SLEEPING_DOG_EFFECT  # -5 п.п. с рекламой

# Итоговая вероятность
p_final = p_purchase.copy()
p_final[treatment == 1] += effect[treatment == 1]
p_final = np.clip(p_final, 0, 1)

# Симулируем покупку
purchase = np.random.binomial(1, p_final)

# Дополнительные фичи
age = np.random.randint(18, 70, NUM_USERS)
income = np.random.normal(50000, 20000, NUM_USERS).clip(10000, 200000)
loyalty_days = np.random.randint(0, 1000, NUM_USERS)
prev_purchases = np.random.poisson(3, NUM_USERS)

df = pd.DataFrame({
    'user_id': np.arange(NUM_USERS),
    'segment': segments,
    'treatment': treatment,
    'purchase': purchase,
    'age': age,
    'income': income.round(0),
    'loyalty_days': loyalty_days,
    'prev_purchases': prev_purchases,
    'base_prob': p_purchase.round(4),
    'final_prob': p_final.round(4),
    'effect': effect.round(4),
})

# Сохраняем
df.to_csv('/opt/airflow/data/uplift_data.csv', index=False)
print(f"Сохранено {len(df)} строк в data/uplift_data.csv")

# Проверка
print("\n=== Распределение по сегментам ===")
print(df.groupby('segment').agg(
    users=('user_id', 'count'),
    conversion_rate=('purchase', 'mean'),
    treatment_share=('treatment', 'mean'),
).round(4))

print("\n=== Uplift по сегментам (test - control) ===")
for seg in [0, 1, 2, 3]:
    sub = df[df['segment'] == seg]
    control = sub[sub['treatment'] == 0]['purchase'].mean()
    test = sub[sub['treatment'] == 1]['purchase'].mean()
    uplift = test - control
    print(f"Segment {seg}: control={control:.4f}, test={test:.4f}, uplift={uplift:+.4f}")

# Общий uplift
control_all = df[df['treatment'] == 0]['purchase'].mean()
test_all = df[df['treatment'] == 1]['purchase'].mean()
print(f"\nОбщий uplift: {test_all - control_all:+.4f}")
