USE SalesCustomerDB;
GO

DECLARE @RunID NVARCHAR(64) = CONVERT(NVARCHAR(36), NEWID());
DECLARE @json NVARCHAR(MAX) =
  (SELECT BulkColumn FROM OPENROWSET(BULK 'C:\SSISData\customer_data.json', SINGLE_CLOB) AS j);

/* Staging contains only the current run. ErrorLog is retained for 90 days. */
TRUNCATE TABLE dbo.Customers_Staging;

SELECT CAST(a.[key] AS INT) + 1 AS SourceRowNum, a.value AS RawRecord,
       j.customer_id, j.customer_name, j.email, j.region, j.join_date, j.loyalty_points,
       lp.[type] AS loyalty_type
INTO #raw
FROM OPENJSON(@json) a
CROSS APPLY OPENJSON(a.value) WITH (
    customer_id    VARCHAR(50),
    customer_name  NVARCHAR(400),
    email          NVARCHAR(400),
    region         NVARCHAR(50),
    join_date      VARCHAR(50),
    loyalty_points NVARCHAR(30)
) j
OUTER APPLY (SELECT [type] FROM OPENJSON(a.value) WHERE [key] = 'loyalty_points') lp;

SELECT SourceRowNum, RawRecord, customer_id AS raw_id,
  LTRIM(RTRIM(ISNULL(customer_id,''))) AS cid,
  ISNULL(NULLIF(LEFT(LTRIM(RTRIM(customer_name)),100),''),'Unknown') AS cname,
  NULLIF(LTRIM(RTRIM(ISNULL(email,''))),'') AS email,
  ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(region,''))),''),'Unknown') AS region,
  TRY_CONVERT(date, LEFT(join_date,10)) AS jd,
  CASE WHEN loyalty_type = 0 OR loyalty_type IS NULL THEN CONVERT(bigint,0)
       WHEN loyalty_type = 2 AND loyalty_points NOT LIKE '%[.eE]%'
            THEN TRY_CONVERT(bigint, loyalty_points)
       ELSE NULL END AS pts,
  CASE WHEN loyalty_type NOT IN (0,2)
         OR (loyalty_type = 2 AND (loyalty_points LIKE '%[.eE]%'
                                  OR TRY_CONVERT(bigint, loyalty_points) IS NULL))
       THEN 'Invalid loyalty_points type/value' END AS reason
INTO #clean
FROM #raw;

UPDATE #clean SET reason = CASE
    WHEN cid = '' THEN 'Missing customer_id'
    WHEN reason IS NOT NULL THEN reason
    WHEN pts < 0 THEN 'Negative loyalty points'
    WHEN email IS NOT NULL AND (CHARINDEX('@',email) < 2 OR CHARINDEX('.',email) = 0 OR LEN(email) > 254)
                   THEN 'Invalid email'
END;

INSERT dbo.Customers_Staging (SourceRowNum, CustomerID, CustomerName, Email, Region, JoinDate, LoyaltyPoints, ETLLoadDate, RunID)
SELECT SourceRowNum, LEFT(cid,20), cname, email, region, jd, pts, SYSUTCDATETIME(), @RunID
FROM #clean WHERE reason IS NULL;

INSERT dbo.ErrorLog (PackageName, SourceRowNum, CustomerID, ErrorReason, RawRecord, RunID)
SELECT 'SQL_fallback_load', SourceRowNum, LEFT(raw_id,20), reason, LEFT(RawRecord,4000), @RunID
FROM #clean WHERE reason IS NOT NULL;

;WITH d AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY CustomerID ORDER BY SourceRowNum DESC) AS rn
    FROM dbo.Customers_Staging WHERE RunID=@RunID
)
MERGE dbo.Customers AS t
USING (SELECT * FROM d WHERE rn = 1) AS s ON t.CustomerID = s.CustomerID
WHEN MATCHED THEN UPDATE SET
     t.CustomerName = s.CustomerName, t.Email = s.Email, t.Region = s.Region,
     t.JoinDate = s.JoinDate, t.LoyaltyPoints = s.LoyaltyPoints
WHEN NOT MATCHED THEN INSERT (CustomerID, CustomerName, Email, Region, JoinDate, LoyaltyPoints)
     VALUES (s.CustomerID, s.CustomerName, s.Email, s.Region, s.JoinDate, s.LoyaltyPoints);

UPDATE d SET CustomerName=c.CustomerName,Email=c.Email,Region=c.Region,JoinDate=c.JoinDate,
             LoyaltyPoints=c.LoyaltyPoints,UpdatedAt=SYSUTCDATETIME()
FROM dbo.DimCustomer d JOIN dbo.Customers c ON c.CustomerID=d.CustomerID;
INSERT dbo.DimCustomer(CustomerID,CustomerName,Email,Region,JoinDate,LoyaltyPoints)
SELECT c.CustomerID,c.CustomerName,c.Email,c.Region,c.JoinDate,c.LoyaltyPoints
FROM dbo.Customers c
WHERE NOT EXISTS (SELECT 1 FROM dbo.DimCustomer d WHERE d.CustomerID=c.CustomerID);

DROP TABLE #raw, #clean;

SELECT @RunID AS run_id, COUNT(*) AS staging_rows FROM dbo.Customers_Staging WHERE RunID=@RunID;
SELECT ErrorReason, COUNT(*) AS n FROM dbo.ErrorLog WHERE RunID=@RunID GROUP BY ErrorReason;
