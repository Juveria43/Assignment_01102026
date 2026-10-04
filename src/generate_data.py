import argparse, copy, json, random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

SEED_RECORDS = [
    {"transaction_id": "T001", "customer_id": "C001", "product": {"id": "P01", "name": "Laptop", "category": "Electronics", "price": 999.99}, "quantity": 2, "discount": 0.05, "date": "2023/01/15 10:30:00", "region": "North"},
    {"transaction_id": "T002", "customer_id": "C002", "product": {"id": "P02", "name": "Mouse", "category": "Accessories", "price": 19.99}, "quantity": 5, "discount": None, "date": "2023-02-10T14:15:00Z", "region": "South"},
    {"transaction_id": "T003", "customer_id": None, "product": {"id": "P03", "name": "Monitor", "category": "Electronics", "price": 299.5}, "quantity": -1, "discount": 0.1, "date": "03-05-2023", "region": "East"},
    {"transaction_id": "T004", "customer_id": "C004", "product": {"id": "P04", "name": "Keyboard", "category": "Accessories", "price": 49.9}, "quantity": 4, "discount": 0.15, "date": "2023-04-20", "region": "West"},
    {"transaction_id": "T005", "customer_id": "C001", "product": {"id": "P05", "name": "Desk", "category": "Furniture", "price": 189.0}, "quantity": 3, "discount": 0, "date": "2023/05/12 12:30:00", "region": "North"},
]

PRODUCTS = [
    ("P01", "Laptop", "Electronics", 999.99),
    ("P02", "Mouse", "Accessories", 19.99),
    ("P03", "Monitor", "Electronics", 299.5),
    ("P04", "Keyboard", "Accessories", 49.9),
    ("P05", "Desk", "Furniture", 189.0),
    ("P06", "Office Chair", "Furniture", 149.0),
    ("P07", "Webcam", "Accessories", 79.0),
    ("P08", "Headphones", "Electronics", 129.99),
    ("P09", "Tablet", "Electronics", 449.0),
    ("P10", "Bookshelf", "Furniture", 119.5),
]
REGIONS = ["North", "South", "East", "West"]
DATE_STYLES = ["%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%m-%d-%Y", "%Y-%m-%d"]


def random_date(rng, start, end):
    return start + timedelta(seconds=rng.randint(0, int((end - start).total_seconds())))


def make_record(rng, txn_id, start, end):
    pid, name, cat, price = rng.choice(PRODUCTS)
    return {
        "transaction_id": txn_id,
        "customer_id": f"C{rng.randint(1, 150):03d}",
        "product": {"id": pid, "name": name, "category": cat, "price": price},
        "quantity": rng.randint(1, 8),
        "discount": rng.choice([None, 0, 0.05, 0.1, 0.15, 0.2]),
        "date": random_date(rng, start, end).strftime(rng.choice(DATE_STYLES)),
        "region": rng.choice(REGIONS),
    }


def inject_dirty(rng, rec, rate):
    if rng.random() > rate:
        return rec
    defect = rng.choice(["null_customer", "neg_qty", "zero_qty", "bad_region",
                         "bad_date", "neg_price", "bad_discount", "missing_product"])
    if defect == "null_customer":
        rec["customer_id"] = None
    elif defect == "neg_qty":
        rec["quantity"] = -rng.randint(1, 3)
    elif defect == "zero_qty":
        rec["quantity"] = 0
    elif defect == "bad_region":
        rec["region"] = rng.choice(["Nrth", "", "Central", None])
    elif defect == "bad_date":
        rec["date"] = rng.choice(["not-a-date", "2023-13-45", "31/31/2023", None])
    elif defect == "neg_price":
        rec["product"]["price"] = -abs(rec["product"]["price"])
    elif defect == "bad_discount":
        rec["discount"] = rng.choice([1.5, -0.2, 7])
    elif defect == "missing_product":
        rec["product"]["id"] = None
    return rec


def build_batch1(rng, n):
    records = copy.deepcopy(SEED_RECORDS)
    start, end = datetime(2023, 1, 1), datetime(2023, 12, 31, 23, 59, 59)
    for i in range(len(records) + 1, n + 1):
        rec = make_record(rng, f"T{i:03d}", start, end)
        records.append(inject_dirty(rng, rec, rate=0.10))
    for _ in range(int(n * 0.02)):                       # exact duplicates
        records.append(copy.deepcopy(rng.choice(records[5:])))
    for _ in range(int(n * 0.01)):                       # same id, different content
        dup = copy.deepcopy(rng.choice(records[5:]))
        dup["quantity"] = (dup["quantity"] if isinstance(dup["quantity"], int) else 1) + 1
        records.append(dup)
    tail = records[5:]
    rng.shuffle(tail)
    return records[:5] + tail


def build_batch2(rng, batch1_path):
    with open(batch1_path, encoding="utf-8") as f:
        old = json.load(f)
    good = [r for r in old if r.get("customer_id") and isinstance(r.get("quantity"), int)
            and r["quantity"] > 0 and r.get("region") in REGIONS
            and r["product"].get("id") and r["product"]["price"] > 0]
    records = []
    for i in range(801, 951):                            # new rows, Jan-Feb 2024
        rec = make_record(rng, f"T{i:03d}", datetime(2024, 1, 1), datetime(2024, 2, 29, 23, 59, 59))
        records.append(inject_dirty(rng, rec, rate=0.05))
    records += [copy.deepcopy(r) for r in rng.sample(good, 15)]     # repeats -> skipped
    for r in rng.sample(good, 5):                                   # changed -> updated
        changed = copy.deepcopy(r)
        changed["quantity"] += 3
        records.append(changed)
    for i in range(951, 954):                                       # late arrivals
        records.append(make_record(rng, f"T{i:03d}", datetime(2023, 11, 1), datetime(2023, 12, 20)))
    rng.shuffle(records)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, choices=[1, 2], default=1)
    parser.add_argument("--rows", type=int, default=800)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed + args.batch)
    DATA_DIR.mkdir(exist_ok=True)
    if args.batch == 1:
        out = DATA_DIR / "sales_data.json"
        records = build_batch1(rng, args.rows)
    else:
        batch1 = DATA_DIR / "sales_data.json"
        if not batch1.exists():
            raise SystemExit("Run batch 1 first: python src/generate_data.py --batch 1")
        out = DATA_DIR / "sales_data_batch2.json"
        records = build_batch2(rng, batch1)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Wrote {len(records)} records -> {out}")


if __name__ == "__main__":
    main()