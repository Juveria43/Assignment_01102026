/* Run after sql/03_ssis_tables_sqlserver.sql in SalesCustomerDB.
   Shared reporting warehouse tables are conformed to the SSIS Customers table. */
USE SalesCustomerDB;
GO

IF OBJECT_ID('dbo.DimCustomer', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimCustomer (
        CustomerID      VARCHAR(20) NOT NULL CONSTRAINT PK_DimCustomer PRIMARY KEY,
        CustomerName    NVARCHAR(100) NULL,
        Email           NVARCHAR(254) NULL,
        Region          NVARCHAR(50) NULL,
        JoinDate        DATE NULL,
        LoyaltyPoints   BIGINT NULL,
        UpdatedAt       DATETIME2 NOT NULL CONSTRAINT DF_DimCustomer_UpdatedAt DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF OBJECT_ID('dbo.DimProduct', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.DimProduct (
        ProductID       VARCHAR(20) NOT NULL CONSTRAINT PK_DimProduct PRIMARY KEY,
        ProductName     NVARCHAR(200) NOT NULL,
        Category        NVARCHAR(100) NOT NULL,
        ListPrice       DECIMAL(19,4) NOT NULL CHECK (ListPrice > 0),
        UpdatedAt       DATETIME2 NOT NULL CONSTRAINT DF_DimProduct_UpdatedAt DEFAULT SYSUTCDATETIME()
    );
END;
GO

IF OBJECT_ID('dbo.FactSales', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.FactSales (
        TransactionID   VARCHAR(50) NOT NULL CONSTRAINT PK_FactSales PRIMARY KEY,
        CustomerID      VARCHAR(20) NOT NULL,
        ProductID       VARCHAR(20) NOT NULL,
        Quantity        INT NOT NULL CHECK (Quantity > 0),
        UnitPrice       DECIMAL(19,4) NOT NULL CHECK (UnitPrice > 0),
        Discount        DECIMAL(9,6) NOT NULL CHECK (Discount BETWEEN 0 AND 1),
        GrossAmount     DECIMAL(19,4) NOT NULL,
        DiscountAmount  DECIMAL(19,4) NOT NULL,
        NetAmount       DECIMAL(19,4) NOT NULL,
        TransactionDate DATETIME2 NOT NULL,
        Region          NVARCHAR(50) NOT NULL,
        RowHash         CHAR(64) NOT NULL,
        SourceFile      NVARCHAR(260) NULL,
        SourceLoadRunID NVARCHAR(32) NULL,
        WarehouseRunID  NVARCHAR(36) NOT NULL,
        LoadedAt        DATETIME2 NOT NULL CONSTRAINT DF_FactSales_LoadedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2 NULL,
        CONSTRAINT FK_FactSales_DimCustomer FOREIGN KEY (CustomerID) REFERENCES dbo.DimCustomer(CustomerID),
        CONSTRAINT FK_FactSales_DimProduct FOREIGN KEY (ProductID) REFERENCES dbo.DimProduct(ProductID)
    );
    CREATE INDEX IX_FactSales_Region_Product_Net ON dbo.FactSales(Region, ProductID) INCLUDE (Quantity, NetAmount);
    CREATE INDEX IX_FactSales_Product_Net ON dbo.FactSales(ProductID) INCLUDE (Quantity, NetAmount);
    CREATE INDEX IX_FactSales_Date_Net ON dbo.FactSales(TransactionDate) INCLUDE (NetAmount);
    CREATE INDEX IX_FactSales_Region_Discount ON dbo.FactSales(Region) INCLUDE (Discount, GrossAmount, DiscountAmount);
    CREATE INDEX IX_FactSales_NetAmount ON dbo.FactSales(NetAmount);
    CREATE INDEX IX_FactSales_Customer ON dbo.FactSales(CustomerID);
END;
GO

IF OBJECT_ID('dbo.WarehouseLoadRun', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.WarehouseLoadRun (
        RunID           NVARCHAR(36) NOT NULL CONSTRAINT PK_WarehouseLoadRun PRIMARY KEY,
        StartedAt       DATETIME2 NOT NULL,
        FinishedAt      DATETIME2 NULL,
        Status          VARCHAR(20) NOT NULL,
        ProductsRead    INT NULL,
        CustomersRead   INT NULL,
        SalesRead       INT NULL,
        SalesInserted   INT NULL,
        SalesUpdated    INT NULL,
        ErrorMessage    NVARCHAR(2000) NULL,
        CHECK (Status IN ('RUNNING','SUCCEEDED','FAILED'))
    );
END;
GO

/* SSIS run-level audit identifiers are retained with stage and rejection rows. */
IF COL_LENGTH('dbo.Customers_Staging', 'RunID') IS NULL
    ALTER TABLE dbo.Customers_Staging ADD RunID NVARCHAR(64) NULL;
ELSE IF COL_LENGTH('dbo.Customers_Staging', 'RunID') < 128
    ALTER TABLE dbo.Customers_Staging ALTER COLUMN RunID NVARCHAR(64) NULL;
IF COL_LENGTH('dbo.ErrorLog', 'RunID') IS NULL
    ALTER TABLE dbo.ErrorLog ADD RunID NVARCHAR(64) NULL;
ELSE IF COL_LENGTH('dbo.ErrorLog', 'RunID') < 128
    ALTER TABLE dbo.ErrorLog ALTER COLUMN RunID NVARCHAR(64) NULL;
GO

/* Keep rejection audit history for 90 days. Schedule daily in SQL Server Agent.
   Staging is transient and is cleared by the package before every load. */
CREATE OR ALTER PROCEDURE dbo.PurgeCustomerEtlAudit
AS
BEGIN
    SET NOCOUNT ON;
    DELETE dbo.ErrorLog WHERE LoggedAt < DATEADD(DAY, -90, SYSUTCDATETIME());
    DELETE dbo.Customers_Staging WHERE ETLLoadDate < DATEADD(DAY, -7, SYSUTCDATETIME());
END;
GO
