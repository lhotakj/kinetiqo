# Database Architecture, Performance Analysis & Recommendations

Kinetiqo supports three enterprise-grade relational database backends: **PostgreSQL**, **MySQL (8.0+) / MariaDB (10+)**, and **Firebird (3.0–5.0)**. 

This document explains the architecture of Kinetiqo's database layer, presents deep technical performance benchmarks, details the architectural differences between engines, and provides production deployment and tuning recommendations.

---

## 1. Database Layer Architecture

Kinetiqo uses a strict **Repository Pattern** with parameterized raw SQL. It explicitly avoids Object-Relational Mappers (ORMs) like SQLAlchemy to eliminate abstraction overhead, maximize query performance, and ensure exact database-level index utilization.

```
┌─────────────────────────────────────────────────────────────┐
│                 Kinetiqo Application Layer                  │
│       (Flask Web UI, DataTables API, Sync Engine, CLI)       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│          DatabaseRepository (Abstract Base Class)           │
│                src/kinetiqo/db/repository.py                │
└──────────────┬───────────────┼───────────────┬──────────────┘
               │               │               │
               ▼               ▼               ▼
      ┌─────────────────┐┌───────────┐┌─────────────────┐
      │   PostgreSQL    ││   MySQL   ││    Firebird     │
      │   Repository    ││Repository ││   Repository    │
      │ (postgresql.py) ││(mysql.py) ││  (firebird.py)  │
      └────────┬────────┘└─────┬─────┘└────────┬────────┘
               │               │               │
               ▼               ▼               ▼
      ┌─────────────────┐┌───────────┐┌─────────────────┐
      │  psycopg2 (C)   ││mysqlclient││firebird-driver  │
      └─────────────────┘└───────────┘└─────────────────┘
```

### Core Architectural Principles:
1. **Zero-ORM Direct SQL Execution**:
   - Queries are written in parameterized SQL (`%s` for PostgreSQL & MySQL, `?` for Firebird).
   - SQL execution plans and index usage are handcrafted for each engine.
2. **Unified Schema Manager (`src/kinetiqo/db/schema.py`)**:
   - On startup, `SchemaManager` validates tables, sequences, and indexes across all backends.
   - Missing tables and indexes are automatically created without manual migration scripts.
3. **Optimized Multi-Column & Covering Indexes**:
   - Composite range-sort indexes (e.g. `idx_activities_start_elev`, `idx_activities_start_dist`) eliminate in-memory sorting penalties.
   - Covering indexes on streams (`idx_streams_activity_lat_lng`) allow Index-Only Scans without reading table heap blocks.

---

## 2. Empirical Performance Benchmarks

The following benchmarks were conducted on identical hardware using dockerized database containers running on default configurations with **629 activities** and **1,761,230 GPS stream points** (a full 365-day athletic history):

```bash
python src/kinetiqo.py benchmark --scope 365 --database [backend]
```

### Benchmark Results Table

| Benchmark Operation | PostgreSQL | MySQL 8.0 | Firebird 5.0 | Primary Performance Factor |
|---|---|---|---|---|
| **Fetch GPS Data (1.76M points)** | **1,701.45 ms (1.70s)** ⚡ | 3,496.56 ms (3.50s) | **22,466.93 ms (22.47s)** ⚠️ | Driver deserialization & Index-Only Scan |
| **Order by Name (`ASC`)** | 15.16 ms | **9.63 ms** ⚡ | 36.34 ms | String collation & PK clustered index |
| **Order by Distance (`DESC`)** | 13.97 ms | **8.25 ms** ⚡ | 35.08 ms | Composite B-Tree index scan |
| **Order by Elevation (`DESC`)** | 13.55 ms | **7.97 ms** ⚡ | 34.58 ms | Composite `(start_date, elevation)` index |

---

## 3. Deep Technical Analysis: Engine & Driver Differences

### Why PostgreSQL Excels at Massive Data Streaming (1.70s)
1. **Native C Driver (`psycopg2` / `libpq`)**:
   - PostgreSQL's `psycopg2` driver is written in compiled C.
   - Parsing binary wire buffers into Python tuples occurs directly in machine code at memory bus speeds with zero Python bytecode execution overhead.
2. **Partial & Covering Indexes**:
   - `CREATE INDEX idx_streams_activity_lat_lng ON streams (activity_id) INCLUDE (lat, lng) WHERE lat IS NOT NULL AND lng IS NOT NULL`
   - Non-GPS activities (gym, swimming, indoor training) are completely excluded from the index.
   - PostgreSQL executes a 100% **Index-Only Scan**, completely bypassing the table heap pages.

---

### Why MySQL is Fastest for Metadata Sorting (7.9–9.6 ms)
1. **Clustered Primary Key Storage (InnoDB)**:
   - In MySQL, the table data is physically stored within the primary key B-Tree clustered index.
   - Once an index scan on `(start_date, total_elevation_gain)` completes, fetching all 26 activity columns from memory pages is near-instantaneous.
2. **Lightweight Byte Collation**:
   - MySQL's default collation (`utf8mb4_general_ci`) performs rapid byte-level comparisons.
   - In contrast, PostgreSQL's `libc` collation (`en_US.UTF-8`) evaluates complex multi-byte Unicode weights during string sorting.

---

### Why Firebird is Slower for Multi-Million Row Streams (~22.4s)
1. **Pure Python DB-API Driver (`firebird-driver`)**:
   - `firebird-driver` is implemented in pure Python using `ctypes`.
   - When transferring 1.76 million rows, the driver executes Python interpreter bytecode for **every single record** to parse the binary XDR wire protocol.
   - Parsing 1.76 million records in Python bytecode takes **~20 seconds of pure CPU time in the Python interpreter process alone**, even though the Firebird server itself finishes disk I/O in ~1.5s.
2. **Default Cache Size (Page Buffers)**:
   - Firebird databases default to `2048` pages of 8KB (only **16 MB RAM cache**). Scanning a 100MB `streams` table causes repeated disk swapping unless page buffers are tuned.
3. **Multi-Version Concurrency Control (MVCC) Record Verification**:
   - During full table or index scans, Firebird inspects record header backversion pointers (`RDB$BACKVERSION`) and the Transaction Inventory Page (TIP) for every row to evaluate visibility.

---

## 4. Production Database Recommendations

| Workload & Deployment Use Case | Recommended Database | Rationale |
|---|---|---|
| **Production Server / Docker / Multi-User** | **PostgreSQL (15+)** | Best overall throughput for large GPS streams, fast Index-Only scans, robust connection pooling, and rich analytical aggregation. |
| **LAMP / LEMP / Fast UI Sorting** | **MySQL (8.0+) / MariaDB** | Blazing-fast DataTables sorting and pagination (7–9 ms), excellent InnoDB buffer pool caching, low memory footprint. |
| **Standalone / Desktop / Embedded** | **Firebird (3.0–5.0)** | Zero-configuration single-file database (`.fdb`), self-contained storage, ideal for embedded single-user instances. |

---

## 5. Performance Tuning Guide

### PostgreSQL Tuning (`postgresql.conf`)
```ini
# Memory cache allocation
shared_buffers = 512MB
work_mem = 32MB
maintenance_work_mem = 128MB
effective_cache_size = 2GB

# Optimizer cost constants for SSD storage
random_page_cost = 1.1
effective_io_concurrency = 200
```

### MySQL Tuning (`my.cnf`)
```ini
[mysqld]
# Ensure entire dataset and indexes fit in RAM
innodb_buffer_pool_size = 1G
innodb_log_file_size = 256M
innodb_flush_log_at_trx_commit = 2
innodb_read_io_threads = 8
```

### Firebird Tuning
For Firebird, increase the database page cache from default (16 MB) to 160 MB using `gfix`:
```bash
# Allocate 20,000 page buffers (approx 160 MB RAM cache for 8KB pages)
gfix -buffers 20000 /path/to/kinetiqo.fdb
```
