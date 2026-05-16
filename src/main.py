from __future__ import annotations
import time
import argparse
import json
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import requests

RAW_DIR = Path("data/raw")
PROC_DIR = Path("data/processed")
FIG_DIR = Path("artifacts/figures")
REP_DIR = Path("artifacts/reports")

# -------------------- IO helpers --------------------
def ensure_dirs():
    for p in [RAW_DIR, PROC_DIR, FIG_DIR, REP_DIR]:
        p.mkdir(parents=True, exist_ok=True)

def save_json(obj: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

# -------------------- COLLECT --------------------
def collect_exchange_rates(start_date="20230101", end_date="20231231", out_name="exchange_rates.json"):
    rates = {}
    currencies = ["usd", "eur", "pln"]
    
    print("Завантаження даних з API НБУ...")
    for valcode in currencies:
        url = f"https://bank.gov.ua/NBU_Exchange/exchange_site?start={start_date}&end={end_date}&valcode={valcode}&sort=exchangedate&order=asc&json"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                rates[valcode.upper()] = r.json()
                print(f"Зібрано дані для: {valcode.upper()}")
                break  # Якщо запит успішний, виходимо з циклу спроб
                
            except requests.exceptions.HTTPError as e:
                if r.status_code in [500, 502, 503, 504]:
                    print(f"Сервер НБУ перевантажений ({r.status_code}). Спроба {attempt + 1} з {max_retries}...")
                    time.sleep(5)  # Чекаємо 5 секунд перед наступною спробою
                else:
                    raise e  # Якщо помилка інша (наприклад, 404), кидаємо ексепшн далі
        
        # Пауза між різними валютами, щоб не спамити сервер НБУ
        time.sleep(2)

    out_path = RAW_DIR / out_name
    out_path.write_text(json.dumps(rates, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Збережено сирі дані: {out_path}")

# -------------------- CLEAN --------------------
def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    info = {}
    info["shape_before"] = list(df.shape)
    info["missing_before"] = int(df.isna().sum().sum())
    info["duplicates_before"] = int(df.duplicated().sum())
    
    # 1. Видалення дублікатів
    df = df.drop_duplicates().copy()
    
    # 2. Обробка пропусків 
    df = df.ffill() # Forward Fill для вихідних/святкових днів
    
    for c in ["USD", "EUR", "PLN"]:
        if df[c].isna().any():
            df[c] = df[c].fillna(df[c].median())

    # 3. Додавання розрахункових колонок (Daily Returns)
    df["USD_return"] = df["USD"].pct_change()
    df["EUR_return"] = df["EUR"].pct_change()
    df["PLN_return"] = df["PLN"].pct_change()
    
    df = df.fillna(0)

    info["shape_after"] = list(df.shape)
    info["missing_after"] = int(df.isna().sum().sum())
    info["duplicates_after"] = int(df.duplicated().sum())
    
    return df, info

# -------------------- VIZ --------------------
def visualize(df: pd.DataFrame, prefix="v8_uah"):
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    
    # 1) Line: Тренд курсів (USD та EUR до UAH)
    p1 = FIG_DIR / f"{prefix}_trend_line.png"
    plt.figure(figsize=(10, 5))
    plt.plot(df.index, df["EUR"], label="EUR/UAH", color="blue")
    plt.plot(df.index, df["USD"], label="USD/UAH", color="green")
    plt.plot(df.index, df["PLN"], label="PLN/UAH", color="red")
    plt.title("Офіційний курс НБУ: USD, EUR та PLN до Гривні (2023 рік)")
    plt.xlabel("Дата")
    plt.ylabel("Гривень за одиницю валюти")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.savefig(p1, bbox_inches="tight")
    plt.close()

    # 2) Histogram: Гістограма daily returns для EUR (бо USD був фіксований частину року)
    p2 = FIG_DIR / f"{prefix}_returns_hist.png"
    plt.figure(figsize=(8, 5))
    df["EUR_return"].hist(bins=50, alpha=0.7, color="blue")
    plt.title("Гістограма щоденної прибутковості (Daily Returns) для EUR/UAH")
    plt.xlabel("Зміна курсу (%)")
    plt.ylabel("Частота (Дні)")
    plt.savefig(p2, bbox_inches="tight")
    plt.close()

    # 3) Rolling STD: Ковзне стандартне відхилення (Зміна волатильності в часі)
    p3 = FIG_DIR / f"{prefix}_rolling_std.png"
    plt.figure(figsize=(10, 5))
    rolling_std_eur = df["EUR"].rolling(window=14).std()
    plt.plot(df.index, rolling_std_eur, color="purple")
    plt.title("Волатильність EUR/UAH (14-денне ковзне стандартне відхилення)")
    plt.xlabel("Дата")
    plt.ylabel("Стандартне відхилення (Гривні)")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.savefig(p3, bbox_inches="tight")
    plt.close()

    # 4) Scatter: Залежність двох європейських валют (EUR vs PLN)
    p4 = FIG_DIR / f"{prefix}_scatter.png"
    plt.figure(figsize=(6, 6))
    plt.scatter(df["EUR"], df["PLN"], alpha=0.5, color="orange")
    plt.title("Залежність курсів: EUR/UAH vs PLN/UAH")
    plt.xlabel("Курс ЄВРО (UAH)")
    plt.ylabel("Курс ЗЛОТОГО (UAH)")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.savefig(p4, bbox_inches="tight")
    plt.close()

    return {"line_trend": str(p1), "hist_returns": str(p2), "rolling_std": str(p3), "scatter_corr": str(p4)}

# -------------------- REPORT --------------------
def make_report(raw_path: Path, clean_path: Path, clean_info: dict, fig_paths: dict):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"# Звіт: Модуль 2 (Варіант 8 - Офіційні курси НБУ)")
    lines.append(f"- **Час генерації**: {ts}")
    lines.append(f"- **Сирий датасет**: `{raw_path}`")
    lines.append(f"- **Очищений датасет**: `{clean_path}`")
    lines.append("")
    lines.append("## Опис очистки даних")
    lines.append("Дані зібрані через API Національного банку України. Оскільки НБУ публікує курси для кожної валюти окремо, вони були об'єднані в єдиний DataFrame за датою. Застосовано `Forward Fill` для заповнення курсів на вихідні дні.")
    lines.append("```json")
    lines.append(json.dumps(clean_info, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Візуалізації")
    for k, v in fig_paths.items():
        if v:
            filename = Path(v).name
            rel_path = f"../figures/{filename}"
            lines.append(f"### {k}")
            lines.append(f"![{k}]({rel_path})")
            lines.append("")
            
    lines.append("## Інтерпретація та висновки")
    lines.append("1. **Фіксований курс**: На графіку `line_trend` чітко видно, що курс USD/UAH був жорстко зафіксований НБУ на рівні 36.56 грн більшу частину 2023 року, і лише восени перейшов у режим керованої гнучкості.")
    lines.append("2. **Динаміка євровалют**: Натомість EUR та PLN коливалися відповідно до ситуації на міжнародних ринках (крос-курси відносно долара).")
    lines.append("3. **Волатильність**: Графік `rolling_std` для Євро показує, що періоди найбільшої нестабільності курсу припадали на середину літа та осінь 2023 року.")
    lines.append("4. **Кореляція європейських ринків**: `scatter_corr` демонструє ідеальну лінійну залежність між Євро та Польським злотим, оскільки економіка Польщі тісно прив'язана до єврозони.")
    lines.append("5. **Практична цінність**: Дані успішно очищені та зведені. Виявлені інсайти щодо фіксованого курсу долара підтверджують важливість аналізу не лише однієї валюти, а цілого кошика для розуміння реальної вартості національних грошей.")
    
    out = REP_DIR / "report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Збережено звіт: {out}")

# -------------------- CLI --------------------
def main():
    ensure_dirs()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c1 = sub.add_parser("collect")
    c1.add_argument("--out", default="exchange_rates_nbu.json")

    cl = sub.add_parser("clean")
    cl.add_argument("--infile", required=True)
    cl.add_argument("--outfile", default="data/processed/clean.csv")

    vz = sub.add_parser("viz")
    vz.add_argument("--infile", required=True)
    vz.add_argument("--prefix", default="v8_uah")

    rp = sub.add_parser("report")
    rp.add_argument("--raw", required=True)
    rp.add_argument("--clean", required=True)
    rp.add_argument("--cleaninfo", required=True)

    args = ap.parse_args()

    if args.cmd == "collect":
        collect_exchange_rates(out_name=args.out)
        
    elif args.cmd == "clean":
        raw_path = Path(args.infile)
        data = json.loads(raw_path.read_text(encoding="utf-8"))
        
        # Парсинг специфічного формату НБУ
        df_list = []
        for currency, records in data.items():
            temp_df = pd.DataFrame(records)
            if not temp_df.empty:
                temp_df = temp_df[["exchangedate", "rate"]]
                temp_df = temp_df.rename(columns={"rate": currency})
                temp_df["exchangedate"] = pd.to_datetime(temp_df["exchangedate"], format="%d.%m.%Y")
                temp_df = temp_df.set_index("exchangedate")
                df_list.append(temp_df)

        if df_list:
            df = pd.concat(df_list, axis=1)
            df.reset_index(names="Date", inplace=True)
            df = df.sort_values("Date")
        else:
            raise ValueError("Немає даних від API НБУ")

        clean_df, info = clean_dataframe(df)
        out_path = Path(args.outfile)
        clean_df.to_csv(out_path, index=False)
        save_json(info, REP_DIR / "clean_info.json")
        print(f"Збережено: {out_path}")

    elif args.cmd == "viz":
        df = pd.read_csv(args.infile)
        figs = visualize(df, prefix=args.prefix)
        save_json(figs, REP_DIR / "fig_paths.json")
        print("Графіки збережено.")

    elif args.cmd == "report":
        clean_info = json.loads(Path(args.cleaninfo).read_text(encoding="utf-8"))
        fig_paths_path = REP_DIR / "fig_paths.json"
        fig_paths = json.loads(fig_paths_path.read_text(encoding="utf-8"))
        make_report(Path(args.raw), Path(args.clean), clean_info, fig_paths)

if __name__ == "__main__":
    main()
