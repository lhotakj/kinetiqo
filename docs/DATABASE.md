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

| Benchmark Operation | PostgreSQL 16 | MySQL 8.0 | Firebird 5.0 | Primary Performance Factor |
|---|---|---|---|---|
| **Fetch GPS Data (1.83M points)** | **1,833.04 ms (1.83s)** ⚡ | 3,846.18 ms (3.85s) | **24,460.89 ms (24.46s)** ⚠️ | Native C wire driver vs. pure-Python deserialization |
| **Order by Name (`ASC`)** | **8.54 ms** ⚡ | 9.69 ms | 37.92 ms | Binary collation (`COLLATE "C"`) & reverse index |
| **Order by Distance (`DESC`)** | 10.43 ms | **8.89 ms** ⚡ | 36.99 ms | Reverse composite `(distance DESC, start_date DESC)` |
| **Order by Elevation (`DESC`)** | **6.93 ms** ⚡ | 12.37 ms | 46.18 ms | Reverse composite `(total_elevation_gain DESC, start_date DESC)` |
| **Paged Grid Fetch (`LIMIT 50`)** | **1.75 ms** ⚡ | 1.85 ms | 6.16 ms | B-Tree index scan with early termination (`LIMIT 50`) |
| **Aggregate Metric Totals** | **0.89 ms** ⚡ | 0.92 ms | 1.87 ms | Covering index `idx_activities_totals_date_cover` (Index-Only scan) |
| **Fitness Suffer Scores** | **1.74 ms** ⚡ | 2.94 ms | 19.64 ms | Tuple unpacking optimization & partial index `idx_activities_fitness_trends` |
| **Activity Count Query** | **0.43 ms** ⚡ | 0.86 ms | 2.23 ms | Header badges & pagination total count (B-Tree index-only count) |

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
   - Once an index scan on `(total_elevation_gain, start_date)` completes, fetching all 27 activity columns from memory pages is near-instantaneous since row data is packed directly in InnoDB 16KB buffer pool pages.
2. **Lightweight Byte Collation**:
   - MySQL's default collation (`utf8mb4_0900_ai_ci` or `utf8mb4_general_ci`) performs rapid byte-level table comparisons.
   - In contrast, PostgreSQL's default `libc` collation (`en_US.UTF-8`) evaluates complex multi-byte Unicode weights through `glibc strcoll()`.

---

### The "Range Predicate Index Trap" & Reverse Composite Indexes
When executing queries that filter by date range and sort by a metric:
```sql
SELECT * FROM activities WHERE start_date >= :since ORDER BY total_elevation_gain DESC;
```
- **The Index Trap**: A composite index ordered as `(start_date DESC, total_elevation_gain DESC)` CANNOT be used to satisfy `ORDER BY total_elevation_gain DESC` because the leading column is evaluated as a range condition (`start_date >= :since`). The matching rows span multiple dates, so their elevation order across dates is non-sequential, forcing the engine into an in-memory Quicksort / Filesort.
- **The Solution (Reverse Composite Indexes)**: Defining indexes in the reverse hierarchy:
  - `idx_activities_elev_start`: `(total_elevation_gain DESC, start_date DESC)`
  - `idx_activities_dist_start`: `(distance DESC, start_date DESC)`
  - `idx_activities_name_start`: `(name COLLATE "C", start_date DESC)` (PostgreSQL) / `(name(191), start_date DESC)` (MySQL) *(Note: Omitted in Firebird because `VARCHAR(500)` UTF-8 + `TIMESTAMP` exceeds Firebird's strict index key limit of `page_size / 4`; Firebird utilizes single-column `idx_activities_name` on `("name")` instead)*
  - `idx_activities_speed_start`: `(average_speed DESC, start_date DESC)`
  - `idx_activities_time_start`: `(moving_time DESC, start_date DESC)`
- **Execution Benefit**: The engine navigates the index in pre-sorted metric order, tests `start_date >= :since` directly on each index tuple, and for paginated queries (`LIMIT 10`, `LIMIT 50`) immediately terminates after finding the required limit, reducing query latency from ~14 ms to **< 0.5 ms**.

---

### PostgreSQL Binary Collation Optimization (`COLLATE "C"`)
When sorting activities by name:
- Standard locale collation (`en_US.UTF-8` or `cs_CZ.UTF-8`) calls `glibc` `strcoll()`, which evaluates case folding, accent decomposition, and multi-weight linguistic keys.
- By defining `idx_activities_name_start` with `(name COLLATE "C", start_date DESC)` and querying with `ORDER BY name COLLATE "C" ASC`, PostgreSQL performs direct binary comparisons (`memcmp`), boosting string sorting speed by **60%–80%**.

---

### Analysis & Optimizations of Analytical & Web Queries (Metrics 5–8)

#### 1. Paged Grid Fetch (`LIMIT 50` — UI DataTables)
- **Engine Behavior**: Both PostgreSQL and MySQL leverage `idx_activities_start_date` to perform a fast B-Tree range scan. Because the query requests `ORDER BY start_date DESC LIMIT 50`, the database engine scans the index in reverse, reads exactly 50 tuples, and immediately stops without scanning remaining rows.
- **Server Execution**: PostgreSQL executes this query in **0.19 ms** (`Buffers: shared hit=43`). MySQL executes without filesort (`"using_filesort": false`) in ~0.25 ms.
- **Firebird Overhead (6.16 ms)**: The query returns 50 rows * 27 columns = 1,350 typed column values. In `psycopg2` and `mysql-connector-python`, row decoding is performed in compiled C extensions. In `firebird-driver`, wire protocol unpacking executes in pure Python bytecode, adding ~4 ms of CPU deserialization overhead.

#### 2. Period Totals Aggregations (`idx_activities_totals_date_cover`)
- **The Problem**: Previously, only `idx_activities_totals_cover (sport, start_date, ...)` existed. Because `sport` was the leading column, queries calculating date-scoped totals without filtering by sport could not use the index and fell back to heap/table scans.
- **Covering Index Optimization**: Added `idx_activities_totals_date_cover`:
  - PostgreSQL: `(start_date) INCLUDE (distance, total_elevation_gain, moving_time)`
  - MySQL: `(start_date, distance, total_elevation_gain, moving_time)`
  - Firebird: `("start_date", "distance", "total_elevation_gain", "moving_time")`
- **Result**: PostgreSQL runs a 100% **Index-Only Scan** (`Heap Fetches: 0`, 7 buffer hits) in **0.20 ms** on the server (0.89 ms total network roundtrip). MySQL uses `"using_index": true`, dropping execution to **0.92 ms**. Firebird drops to **1.87 ms**.

#### 3. Fitness Suffer Scores & Python Deserialization Overhead
- **Server-Side Plan**: PostgreSQL already had the partial covering index:
  `CREATE INDEX idx_activities_fitness_trends ON activities (start_date) INCLUDE (suffer_score) WHERE suffer_score > 0`.
  The database engine executes the query in **0.13 ms** (`Heap Fetches: 0`, 8 buffer hits).
- **Python Driver Bottleneck**: In `postgresql.py` and `mysql.py`, the queries previously instantiated dictionary cursors (`RealDictCursor` and `dictionary=True`) and then iterated over all ~600 rows doing `dict(row)`. This created over 1,200 dictionary allocations and repeated key lookups in Python bytecode, taking ~2.5 ms in Python alone.
- **Tuple Unpack Optimization**: Switching to standard tuple cursors with direct list comprehension:
  ```python
  activities = [
      {'start_date': dt.isoformat() if isinstance(dt, datetime) else dt, 'suffer_score': score}
      for dt, score in cur.fetchall()
  ]
  ```
  PostgreSQL query time dropped from **4.11 ms down to 1.74 ms** (a **2.3x speedup**), and MySQL dropped to **2.94 ms**.

#### 4. Activity Count Query (`count_activities`)
- **Execution**: `SELECT COUNT(*) FROM activities WHERE start_date >= %s` executes as an Index-Only scan on `idx_activities_start_date` across all three engines.
- **Performance**: Executing in **0.43 ms** (PostgreSQL), **0.86 ms** (MySQL), and **2.23 ms** (Firebird). At < 1 ms, this is at the physical network TCP socket floor.

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
| **LAMP / LEMP / Fast UI Sorting** | **MySQL (8.0+) / MariaDB** | Blazing-fast DataTables sorting and pagination (1–2 ms with reverse indexes), excellent InnoDB buffer pool caching, low memory footprint. |
| **Standalone / Desktop / Embedded** | **Firebird (3.0–5.0)** | Zero-configuration single-file database (`.fdb`), self-contained storage, ideal for embedded single-user instances. |

---

## 5. Performance Tuning Guide

### PostgreSQL Tuning (`postgresql.conf`)
```ini
# Memory cache allocation
shared_buffers = 512MB
work_mem = 64MB
maintenance_work_mem = 128MB
effective_cache_size = 2GB

# Disable JIT compilation for OLTP/web queries (eliminates 10-20ms planner overhead)
jit = off

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
sort_buffer_size = 4M
```

### Firebird Tuning
For Firebird, expand the database page cache from default (16 MB) to 200 MB using `gfix`:
```bash
# Allocate 25,000 page buffers (approx 200 MB RAM cache for 8KB pages)
gfix -buffers 25000 /path/to/kinetiqo.fdb
```
