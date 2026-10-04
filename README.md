# Sales and Customer Data Pipeline

This project processes sales transactions from JSON with Python and customer data with SSIS. Python loads sales data into SQLite. A daily Python ETL publishes the sales data to SQL Server, where the customer pipeline and reporting warehouse are available together.

## Project structure

| Path | Purpose |
|---|---|
| `data/sales_data.json` | Generated sales batch 1 (824 records) |
| `data/sales_data_batch2.json` | Incremental sales batch 2 (173 records) |
| `data/customer_data.json` | Customer source for SSIS (105 records) |
| `src/etl_pipeline.py` | Python sales ETL into SQLite |
| `src/generate_data.py` | Generates test batches from the supplied sample data |
| `src/sync_sqlite_to_sqlserver.py` | Daily publication from SQLite to the SQL Server warehouse |
| `src/show_results.py` | Shows SQLite row counts, run history and summary results |
| `src/run_part2.py` | Runs the Part 2 SQLite queries |
| `src/benchmark_indexes.py` | Compares query timings with different index sets |
| `sql/schema_sqlite.sql` | SQLite sales schema |
| `sql/part2/` | Analytical views, indexes and query scripts |
| `sql/03_ssis_tables_sqlserver.sql` | SQL Server database and SSIS customer tables |
| `sql/04_warehouse_sqlserver.sql` | Shared SQL Server dimensions, fact table, audit and retention procedure |
| `ssis/CustomerETL/` | SSIS solution and `LoadCustomers.dtsx` package |
| `Power BI/SalesCustomerDashboard.pbix` | Power BI dashboard |
| `docs/part2_sample_output.md` | SQL queries, sample results and query plans |
| `docs/part2_design_and_indexing.md` | Schema and index design notes |
| `docs/screenshots/`, `Screenshots/` | Python and SSIS screenshots |
| `logs/` | ETL log and rejected-row files from sample runs |
| `tests/` | Unit tests for product change detection |

## Requirements

- Python 3.10 or later and the packages in `requirements.txt`
- SQLite, included with Python
- SQL Server and Microsoft ODBC Driver 18 for SQL Server for warehouse publishing
- For SSIS: Windows, Visual Studio with the SSIS Projects extension, and SQL Server
- Power BI Desktop to open the dashboard

## Run the Python sales pipeline

From the repository root:

```bash
python -m venv .venv
```

Activate the environment and install the packages:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS or Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Generate the sample data, run both sales batches, then run the Part 2 queries:

```bash
python src/generate_data.py --batch 1
python src/etl_pipeline.py --input data/sales_data.json --reset
python src/generate_data.py --batch 2
python src/etl_pipeline.py --input data/sales_data_batch2.json
python src/show_results.py
python src/run_part2.py
```

The Python sales pipeline uses SQLite and applies `sql/schema_sqlite.sql` when it initializes `db/sales.db`. `--reset` starts a clean initial load; omit it for incremental runs.

## Shared SQL Server warehouse

The warehouse lives in SQL Server `SalesCustomerDB`. SSIS loads customer attributes from JSON into `dbo.Customers` and then refreshes the conformed `dbo.DimCustomer`. The daily sales publish reads the SQLite `dim_customer`, `dim_product` and `fact_sales` tables and upserts them into SQL Server `dbo.DimCustomer`, `dbo.DimProduct` and `dbo.FactSales`.

The fact table has a primary key on `TransactionID` and foreign keys to `DimCustomer.CustomerID` and `DimProduct.ProductID`. Product and customer IDs are primary keys in their dimension tables. Sales-only customer IDs are inserted into `DimCustomer` with descriptive fields left NULL; a later SSIS customer load fills those attributes. This keeps the sales fact load valid when the customer source does not yet contain every sales ID.

The Python ETL is already built and tested against SQLite, and SSIS already uses SQL Server. I kept those source pipelines in place and added one daily idempotent publish from SQLite to SQL Server. This avoids rewriting the working sales loader and lets the SQL Server warehouse be the shared reporting store. For the current test data, the publisher reads a full snapshot each day and inserts new rows or updates facts whose row hash changed. Re-running it is safe. A full scan is straightforward at this data size; a larger deployment should switch to a source change watermark or CDC and retain the same idempotent keys.

### Create the SQL Server warehouse

Run these scripts in order in SSMS:

```text
sql/03_ssis_tables_sqlserver.sql
sql/04_warehouse_sqlserver.sql
```

Set the connection string outside the repository. Example for local Windows authentication:

```powershell
$env:SQLSERVER_CONNECTION_STRING = 'Driver={ODBC Driver 18 for SQL Server};Server=localhost\SQLEXPRESS01;Database=SalesCustomerDB;Trusted_Connection=yes;TrustServerCertificate=yes;'
python src/sync_sqlite_to_sqlserver.py
```

On a clean run, load sales JSON into SQLite and load customer JSON through SSIS, then publish sales. Sales-only IDs are created as dimension rows automatically. Schedule the source loaders and `python src/sync_sqlite_to_sqlserver.py` once a day using Task Scheduler or an equivalent scheduler; run the publisher after the SQLite sales load. `dbo.WarehouseLoadRun` records each run, row counts and its outcome. A failed publish rolls back the warehouse changes and records the failed run; the next run can safely retry.

## Part 1: Python sales ETL

### Transformations and validation

The pipeline reads the nested `product` object and flattens its fields. It trims text, standardizes IDs and regions, parses the supported date formats, and calculates gross, discount and net amounts. A null discount is treated as zero. The date `03-05-2023` is interpreted as March 5, 2023 (MM-DD-YYYY).

Rows are rejected when required IDs are missing, price or quantity is not positive, discount is outside 0–1, the date cannot be parsed, the region is invalid, or a transaction ID is duplicated within an input file. Rejection reasons and source rows are retained for review. In the sample data, T003 is rejected because its customer ID is missing and quantity is negative.

### Incremental load

The pipeline compares transaction IDs and a SHA-256 hash of the business fields with rows already in `fact_sales`:

- New transaction ID: insert the transaction.
- Existing ID with changed hash: update the transaction.
- Existing ID with the same hash: skip it.
- Late arriving transactions are logged and inserted even when their date is earlier than the current watermark.

The hash includes customer ID, product ID, product name, product category, quantity, price, discount, date and region. The fields are serialized as JSON before hashing to avoid separator collisions. A product rename or category change therefore triggers a fact update and refreshes the SQLite product dimension. If you reuse a database created with the earlier hash, the first rerun may update existing facts once as the hash format changes. Loads are committed in a database transaction. Re-running an unchanged batch is idempotent. Rejected records are logged on each run, so rerunning a batch can add another rejection audit entry for the same source row.

### Sample run results

These results are from the included test batches:

| Run | Read | Rejected | Inserted | Updated | Skipped |
|---|---:|---:|---:|---:|---:|
| Initial load | 824 | 117 | 707 | 0 | 0 |
| Batch 2 | 173 | 8 | 145 | 5 | 15 |
| Batch 2 rerun | 173 | 8 | 0 | 0 | 165 |

The final sample SQLite database contains 852 sales rows, 10 products and 149 customers. The rejected-record count includes rejections recorded from all three runs.

## Part 2: Database design and SQL

`sql/schema_sqlite.sql` defines the local sales schema. Its main tables are `fact_sales`, `dim_product` and `dim_customer`. The fact table has a transaction primary key and customer/product foreign keys. Product and customer attributes are stored separately. Derived gross, discount and net amounts are retained on fact rows for reporting and indexing.

`sql/part2/03_queries.sql` covers sales by region and category, top five products, monthly sales, average discount by region, and transactions over $1,000. Example output and `EXPLAIN QUERY PLAN` results are in [`docs/part2_sample_output.md`](docs/part2_sample_output.md). Index choices and benchmark measurements are in [`docs/part2_design_and_indexing.md`](docs/part2_design_and_indexing.md). Indexes improve selected reads but use storage and add work to inserts and updates.

The shared SQL Server schema is in `sql/04_warehouse_sqlserver.sql`. The SQL Server query variant expects those warehouse tables; the primary analytical query scripts and sample outputs use SQLite.

## Part 3: SSIS customer pipeline

The SSIS package reads `data/customer_data.json`, validates and transforms customer records, writes valid rows to a staging table, and merges them into `dbo.Customers`. It then updates the shared `dbo.DimCustomer`. Rejected rows go to `dbo.ErrorLog`.

### Run the package

1. Run `sql/03_ssis_tables_sqlserver.sql` and `sql/04_warehouse_sqlserver.sql` in SSMS.
2. Open `ssis/CustomerETL/CustomerETL.slnx` in Visual Studio with the SSIS Projects extension.
3. Set `ServerName`, `DatabaseName` and `SourceFilePath` in `Project.params`. Set `SourceFilePath` to the full path of this repository's `data/customer_data.json`; the checked-in default path is machine-specific.
4. Open the `Read Customer JSON` Script Component once in the SSIS script editor, save/build its script, then rebuild and run `LoadCustomers.dtsx`. The embedded script source and output metadata changed, so Visual Studio must regenerate the compiled Script Component assembly.
5. Verify row counts and audit records in SQL Server.

The package uses Windows authentication through its project connection expression. `ErrorFilePath` is defined as a parameter, but the current package writes rejected rows to `dbo.ErrorLog`; it does not write an error file.

### Data flow and validation

The control flow clears `Customers_Staging`, runs a Data Flow Task, then merges staged rows into `Customers` and updates `DimCustomer`. The data flow uses a C# Script Component as the JSON source, a Row Count, Derived Column transformations and a Conditional Split.

| Input condition | Package action |
|---|---|
| Missing or blank customer ID | Reject to `ErrorLog` |
| Negative loyalty points | Reject to `ErrorLog` |
| Loyalty points is a string, fractional number or outside the integer range | Reject to `ErrorLog` |
| JSON null or missing loyalty points | Default to 0 |
| Malformed or overlength email | Reject to `ErrorLog` |
| Null or blank name/region | Set to `Unknown` |
| Null or blank email | Load as NULL |
| Unparseable join date | Load as NULL |
| Duplicate customer ID | Keep the last occurrence in the current run |

The Script Component preserves JSON scalar types for `loyalty_points`. Only an integer JSON number is accepted. A malformed string or fractional value is routed to the reject flow before the null-to-zero default can run.

The sample run reads 105 rows: 24 are rejected (19 invalid emails, 4 negative loyalty values and 1 missing customer ID). The remaining 81 rows are staged, then de-duplicated to 76 customers.

```sql
SELECT COUNT(*) FROM dbo.Customers_Staging; -- rows from the latest run
SELECT COUNT(*) FROM dbo.Customers;
SELECT RunID, ErrorReason, COUNT(*)
FROM dbo.ErrorLog
GROUP BY RunID, ErrorReason
ORDER BY RunID DESC;
```

### Run ID and retention

The Script Component creates one timestamp-prefixed run ID per data-flow execution and writes it to every staging row and rejected audit row as `RunID`. The timestamp prefix lets the merge select the latest run if a checkpoint restart leaves partial rows from a failed attempt. The merge reads only the current staged run. The package clears staging before each execution; staging is operational data and is not kept as history. `ErrorLog` rows are retained for 90 days. Schedule `dbo.PurgeCustomerEtlAudit` from `sql/04_warehouse_sqlserver.sql` as a daily SQL Server Agent job. The procedure also removes any staging rows older than seven days as a cleanup safeguard.

The package has `SaveCheckpoints = True`, `CheckpointUsage = IfExists` and `FailPackageOnFailure = True`. Its checkpoint path is currently configured as `C:\SSISData\LoadCustomers.chk`; change it for the machine where the package runs. Checkpoints restart at task boundaries. If the Data Flow partially writes rows and then fails, rerun after reviewing/clearing the partial staging rows; error rows remain available by `RunID` until the retention period expires. Schedule only one instance of this package at a time because the staging table is cleared at the beginning of a run.

### SQL fallback

`sql/03_load_customers_fallback.sql` applies the customer validation and merge with SQL Server `OPENJSON`. It now assigns its own run ID, retains error records, rejects malformed loyalty values, and updates the same conformed customer dimension. Set the JSON file path in that script before running it.

## Part 4: Power BI dashboard

Open [`Power BI/SalesCustomerDashboard.pbix`](Power%20BI/SalesCustomerDashboard.pbix) in Power BI Desktop. Verify or change its data source to the shared SQL Server warehouse before enabling refresh. The report contains these visuals:

- Total sales by region
- Monthly sales trend
- Top five products by revenue
- Total Customers and Average Sale per Transaction KPI cards
- Loyalty points distribution by region
- High-Value Transactions KPI card

The current PBIX includes an additional High-Value Transactions KPI card. Apply the requested dashboard changes to the PBIX before submission if they have not already been made. The dashboard screenshot is not included in the repository. The PBIX DAX expressions have not been verified independently, so the following describes the intended calculations and should be checked in Power BI Desktop:

| Measure | Intended calculation |
|---|---|
| Total Sales | Sum of transaction net amounts |
| Average Sale per Transaction | Total sales divided by the distinct transaction count |
| Total Loyalty Points | Sum of customer loyalty points |
| High-Value Transactions | Count of transactions where net amount is greater than 1,000 |
| Sales YTD | Total sales from the start of the year through the selected date |

The requested Sales YTD measure is not confirmed in the available report review. Add or verify it in Power BI Desktop, and capture a screenshot of the final dashboard for the submission.

The sample SQL results show that Electronics has the highest sales in each region, and Laptop is the top product by revenue. Sales vary by month; January 2024 is the highest month in the sample output. North has the highest average discount in the sample data. Refresh these observations if the data changes.

## Logging and screenshots

The Python sales pipeline writes stage summaries and validation messages to `logs/etl_pipeline.log`. It also writes rejected rows to `logs/rejected_<run_id>.csv`. SSIS rejects are stored in SQL Server `dbo.ErrorLog` with `RunID`.

![Python initial load](docs/screenshots/01_initial_load.png)

![Python incremental load](docs/screenshots/02_incremental_load.png)

![Python batch rerun](docs/screenshots/03_rerun.png)

![Python tables and run history](docs/screenshots/04_tables.png)

![Python rejected records](docs/screenshots/05_rejections.png)

![Python log file](docs/screenshots/06_log_file.png)

![SSIS control flow](Screenshots/03_control_flow_success.png)

![SSIS data flow with row counts](Screenshots/03_data_flow_rowcounts.png)

![SSIS SQL verification](Screenshots/03_sql_verification.png)

The Power BI dashboard screenshot and SSIS checkpoint settings screenshot are not included and still need to be captured for the assignment.

## Tests

Run the unit test for the Python product change-detection hash with:

```bash
python -m unittest discover -s tests
```

The SSIS package needs Windows and the SSIS Projects extension. The Python publisher needs pyodbc, Microsoft ODBC Driver 18 and SQL Server. Both were validated structurally here, but neither was executed against a live SQL Server instance. The existing SSIS screenshots predate the run ID and validation changes; recapture them after a successful run.

## Production improvements

- Replace the daily full snapshot with change tracking or CDC when the sales volume makes a full scan expensive.
- Add an automated SQL Server/ODBC integration test in a disposable database and test SSIS restart behavior after partial data-flow writes.
- Add secrets and environment-specific paths outside source control. Use SQL Server Agent or an orchestrator to schedule the SSIS package, daily warehouse publish and 90-day audit purge, with monitoring and failure alerts.
- Keep Python and SSIS audit run IDs and source metadata through the warehouse so each report row can be traced back to its load.
