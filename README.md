# Модуль 2: Автоматизований збір та аналіз курсів валют

Програма призначена для автоматичного збору офіційних курсів валют (USD, EUR, PLN) з API Національного банку України за 2023 рік, їх очищення, аналізу волатильності та генерації звіту з візуалізаціями.

## Інструкція із запуску

Всі команди виконуються послідовно з кореневої директорії проєкту:

### Крок 1: Збір даних з API НБУ
python src/main.py collect --out exchange_rates.json

### Крок 2: Обробка та очищення даних
python src/main.py clean --infile data/raw/exchange_rates.json --outfile data/processed/clean.csv

### Крок 3: Візуалізація та генерація графіків
python src/main.py viz --infile data/processed/clean.csv

### Крок 4: Створення фінального аналітичного звіту
python src/main.py report --raw data/raw/exchange_rates.json --clean data/processed/clean.csv --cleaninfo artifacts/reports/clean_info.json

## Результати
Після виконання всіх кроків у папці `artifacts/figures/` з'являться 4 графіки волатильності та трендів, а у папці `artifacts/reports/` буде згенеровано підсумковий аналітичний звіт `report.md`.