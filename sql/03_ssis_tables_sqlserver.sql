IF DB_ID(N'SalesCustomerDB') IS NULL
    CREATE DATABASE SalesCustomerDB;
GO
USE SalesCustomerDB;
GO

CREATE TABLE dbo.Customers (
    CustomerID    VARCHAR(20)   NOT NULL PRIMARY KEY,
    CustomerName  NVARCHAR(100) NOT NULL,
    Email         NVARCHAR(254) NULL,
    Region        NVARCHAR(50)  NOT NULL,
    JoinDate      DATE          NULL,
    LoyaltyPoints BIGINT        NOT NULL,
    LoadedAt      DATETIME2     NOT NULL DEFAULT SYSDATETIME()
);

CREATE TABLE dbo.Customers_Staging (
    SourceRowNum  INT           NOT NULL,
    CustomerID    VARCHAR(20)   NOT NULL,
    CustomerName  NVARCHAR(100) NOT NULL,
    Email         NVARCHAR(254) NULL,
    Region        NVARCHAR(50)  NOT NULL,
    JoinDate      DATE          NULL,
    LoyaltyPoints BIGINT        NOT NULL,
    ETLLoadDate   DATETIME2     NOT NULL,
    RunID         NVARCHAR(64)  NULL
);

CREATE TABLE dbo.ErrorLog (
    ErrorID      INT IDENTITY(1,1) PRIMARY KEY,
    PackageName  NVARCHAR(100),
    SourceRowNum INT,
    CustomerID   VARCHAR(20) NULL,
    ErrorReason  NVARCHAR(200),
    RawRecord    NVARCHAR(4000),
    LoggedAt     DATETIME2 DEFAULT SYSUTCDATETIME(),
    RunID        NVARCHAR(64) NULL
);