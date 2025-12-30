IF DB_ID('DeliveryOptimizationDB') IS NULL
BEGIN
    CREATE DATABASE DeliveryOptimizationDB;
END
GO

USE DeliveryOptimizationDB;
GO

------------------------------------------------------------
-- 1. Create schema
------------------------------------------------------------
CREATE SCHEMA wh;
GO

------------------------------------------------------------
-- 2. Core reference tables: TruckType, Truck
------------------------------------------------------------

-- 2.1 TruckType
CREATE TABLE wh.TruckType (
    Type_id         INT IDENTITY(1,1) PRIMARY KEY,
    Name            NVARCHAR(50)  NOT NULL,   -- Small / Medium / Large
    Length_cm       INT           NOT NULL,   -- interior length
    Width_cm        INT           NOT NULL,
    Height_cm       INT           NOT NULL,
    Max_weight_lbs  DECIMAL(10,2) NOT NULL,   -- capacity in pounds

    CONSTRAINT CK_TruckType_PositiveDims
        CHECK (Length_cm > 0 AND Width_cm > 0 AND Height_cm > 0 AND Max_weight_lbs > 0)
);
GO

-- 2.2 Truck
CREATE TABLE wh.Truck (
    Truck_id    INT IDENTITY(1,1) PRIMARY KEY,
    Type_id     INT          NOT NULL,
    Label       NVARCHAR(50) NOT NULL,   -- e.g. 'Van-01'
    Status      NVARCHAR(20) NOT NULL,   -- AVAILABLE / OUT_OF_SERVICE

    CONSTRAINT FK_Truck_TruckType
        FOREIGN KEY (Type_id) REFERENCES wh.TruckType(Type_id)
);
GO

------------------------------------------------------------
-- 3. Customer, Address, Product, Sale_Order
------------------------------------------------------------

-- 3.1 Customer
CREATE TABLE wh.Customer (
    Cust_id     INT IDENTITY(1,1) PRIMARY KEY,
    Full_name   NVARCHAR(80) NOT NULL,
    Email       NVARCHAR(80) NOT NULL,
    Phone       NVARCHAR(20) NULL
);
GO

-- 3.2 Address
CREATE TABLE wh.Address (
    Address_id      INT IDENTITY(1,1) PRIMARY KEY,
    Cust_id         INT            NULL,       -- optional: address can belong to a customer
    Address_line1   NVARCHAR(120)  NOT NULL,
    Address_line2   NVARCHAR(120)  NULL,
    City            NVARCHAR(80)   NOT NULL,
    State           NVARCHAR(40)   NOT NULL,
    Postal_code     NVARCHAR(20)   NOT NULL,
    Country         NVARCHAR(60)   NOT NULL DEFAULT N'USA',
    Latitude        DECIMAL(9,6)   NULL,
    Longitude       DECIMAL(9,6)   NULL,

    CONSTRAINT FK_Address_Customer
        FOREIGN KEY (Cust_id) REFERENCES wh.Customer(Cust_id)
);
GO

-- 3.3 Product
CREATE TABLE wh.Product (
    Prod_id      NVARCHAR(20)  PRIMARY KEY,  -- SKU
    Name         NVARCHAR(100) NOT NULL,
    Category     NVARCHAR(50)  NULL,
    Weight_lbs   DECIMAL(10,2) NOT NULL,
    Length_cm    INT           NOT NULL,
    Width_cm     INT           NOT NULL,
    Height_cm    INT           NOT NULL,

    CONSTRAINT CK_Product_PositiveDims
        CHECK (Weight_lbs > 0 AND Length_cm > 0 AND Width_cm > 0 AND Height_cm > 0)
);
GO

-- 3.4 Sale_Order (order header)
CREATE TABLE wh.Sale_Order (
    SOrder_num    INT IDENTITY(1,1) PRIMARY KEY,
    Cust_id       INT           NOT NULL,
    Order_date    DATE          NOT NULL,
    Order_status  NVARCHAR(20)  NOT NULL,    -- NEW / SHIPPED / DELIVERED / CANCELED

    CONSTRAINT FK_SaleOrder_Customer
        FOREIGN KEY (Cust_id) REFERENCES wh.Customer(Cust_id)
);
GO

------------------------------------------------------------
-- 4. Package and routing core: Package, Dispatch, DispatchStop, PackageAssignment
------------------------------------------------------------

-- 4.1 Package
CREATE TABLE wh.Package (
    Package_id    NVARCHAR(40)  PRIMARY KEY,    -- QR / barcode
    Address_id    INT           NOT NULL,       -- destination address
    Weight_lbs    DECIMAL(10,2) NOT NULL,
    Length_cm     INT           NOT NULL,
    Width_cm      INT           NOT NULL,
    Height_cm     INT           NOT NULL,
    Fragile_flag  BIT           NOT NULL,       -- 0 = normal, 1 = fragile
    Status        NVARCHAR(20)  NOT NULL,       -- CREATED / INBOUND / LOADED / OUTBOUND / DELIVERED
    Created_ts    DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT FK_Package_Address
        FOREIGN KEY (Address_id) REFERENCES wh.Address(Address_id),

    CONSTRAINT CK_Package_PositiveDims
        CHECK (Weight_lbs > 0 AND Length_cm > 0 AND Width_cm > 0 AND Height_cm > 0)
);
GO

-- 4.2 Dispatch
CREATE TABLE wh.Dispatch (
    Dispatch_id   INT IDENTITY(1,1) PRIMARY KEY,
    Truck_id      INT           NOT NULL,
    Service_date  DATE          NOT NULL,
    Status        NVARCHAR(20)  NOT NULL,  -- PLANNED / LOADING / OUTBOUND / COMPLETE

    CONSTRAINT FK_Dispatch_Truck
        FOREIGN KEY (Truck_id) REFERENCES wh.Truck(Truck_id)
);
GO

-- 4.3 DispatchStop
CREATE TABLE wh.DispatchStop (
    Stop_id      INT IDENTITY(1,1) PRIMARY KEY,
    Dispatch_id  INT NOT NULL,
    Address_id   INT NOT NULL,
    Sequence     INT NOT NULL,   -- 1 = first stop

    CONSTRAINT FK_DispatchStop_Dispatch
        FOREIGN KEY (Dispatch_id) REFERENCES wh.Dispatch(Dispatch_id),

    CONSTRAINT FK_DispatchStop_Address
        FOREIGN KEY (Address_id) REFERENCES wh.Address(Address_id),

    CONSTRAINT UQ_DispatchStop_Dispatch_Sequence
        UNIQUE (Dispatch_id, Sequence),

    CONSTRAINT CK_DispatchStop_Sequence_Positive
        CHECK (Sequence >= 1)
);
GO

-- 4.4 PackageAssignment (1:1 with Package in prototype)
CREATE TABLE wh.PackageAssignment (
    Package_id   NVARCHAR(40) PRIMARY KEY,   -- PK + FK → one assignment per package
    Stop_id      INT          NOT NULL,
    Assigned_ts  DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT FK_PackageAssignment_Package
        FOREIGN KEY (Package_id) REFERENCES wh.Package(Package_id),

    CONSTRAINT FK_PackageAssignment_DispatchStop
        FOREIGN KEY (Stop_id) REFERENCES wh.DispatchStop(Stop_id)
);
GO

------------------------------------------------------------
-- 5. Load plan + placement (3D layout)
------------------------------------------------------------

-- 5.1 LoadPlan
CREATE TABLE wh.LoadPlan (
    Loadplan_id       INT IDENTITY(1,1) PRIMARY KEY,
    Dispatch_id       INT           NOT NULL,
    Generated_ts      DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    Algorithm_version NVARCHAR(40)  NOT NULL,
    Util_weight_pct   DECIMAL(5,2)  NOT NULL,
    Util_volume_pct   DECIMAL(5,2)  NOT NULL,

    CONSTRAINT FK_LoadPlan_Dispatch
        FOREIGN KEY (Dispatch_id) REFERENCES wh.Dispatch(Dispatch_id)
);
GO

-- 5.2 Placement
CREATE TABLE wh.Placement (
    Placement_id       INT IDENTITY(1,1) PRIMARY KEY,
    Loadplan_id        INT           NOT NULL,
    Package_id         NVARCHAR(40)  NOT NULL,
    X_cm               INT           NOT NULL,
    Y_cm               INT           NOT NULL,
    Z_cm               INT           NOT NULL,
    Length_cm          INT           NOT NULL,
    Width_cm           INT           NOT NULL,
    Height_cm          INT           NOT NULL,
    Rotated_base_flag  BIT           NOT NULL,   -- 1 = rotated on base
    Layer_index        INT           NOT NULL,

    CONSTRAINT FK_Placement_LoadPlan
        FOREIGN KEY (Loadplan_id) REFERENCES wh.LoadPlan(Loadplan_id),

    CONSTRAINT FK_Placement_Package
        FOREIGN KEY (Package_id)  REFERENCES wh.Package(Package_id),

    CONSTRAINT CK_Placement_PositiveDims
        CHECK (Length_cm > 0 AND Width_cm > 0 AND Height_cm > 0),

    CONSTRAINT CK_Placement_NonNegativeCoords
        CHECK (X_cm >= 0 AND Y_cm >= 0 AND Z_cm >= 0),

    CONSTRAINT UQ_Placement_LoadPlan_Package
        UNIQUE (Loadplan_id, Package_id)     -- one placement per package per plan
);
GO

------------------------------------------------------------
-- 6. Order lines: link orders, products, and packages
------------------------------------------------------------

CREATE TABLE wh.SOrder_Line (
    SOrder_num   INT            NOT NULL,   -- FK + part of PK
    Prod_id      NVARCHAR(20)   NOT NULL,   -- FK + part of PK
    Package_id   NVARCHAR(40)   NOT NULL,   -- FK to Package
    Quantity     INT            NOT NULL,
    Unit_price   DECIMAL(10,2)  NOT NULL,

    CONSTRAINT PK_SOrder_Line
        PRIMARY KEY (SOrder_num, Prod_id),

    CONSTRAINT FK_SOrderLine_SaleOrder
        FOREIGN KEY (SOrder_num) REFERENCES wh.Sale_Order(SOrder_num),

    CONSTRAINT FK_SOrderLine_Product
        FOREIGN KEY (Prod_id)    REFERENCES wh.Product(Prod_id),

    CONSTRAINT FK_SOrderLine_Package
        FOREIGN KEY (Package_id) REFERENCES wh.Package(Package_id),

    CONSTRAINT CK_SOrderLine_PositiveQty
        CHECK (Quantity > 0),

    CONSTRAINT CK_SOrderLine_NonNegativePrice
        CHECK (Unit_price >= 0)
);
GO
