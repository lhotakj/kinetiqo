jarda@home:~/WORKING/kinetiqo/src$ ./kinetiqo.py benchmark --database mysql && ./kinetiqo.py benchmark --database postgresql && ./kinetiqo.py benchmark --database firebird
2026-08-30 23:56:44 [INFO] Running database benchmark (backend=MYSQL, scope=365 days)...

==========================================================================
  Kinetiqo Database Benchmark (MYSQL)
  Scope: Last 365 days
==========================================================================
  * Fetch all GPS data for last 365 days all activity types: 3467.51 ms (1,761,230 records)
  * Order all activities by name:                             12.39 ms (629 activities)
  * Order all activities by distance:                         8.19 ms (629 activities)
  * Order all activities by elevation gained:                 8.34 ms (629 activities)
==========================================================================

2026-08-30 23:56:47 [INFO] Running database benchmark (backend=POSTGRESQL, scope=365 days)...

==========================================================================
  Kinetiqo Database Benchmark (POSTGRESQL)
  Scope: Last 365 days
==========================================================================
  * Fetch all GPS data for last 365 days all activity types: 1672.33 ms (1,761,230 records)
  * Order all activities by name:                             16.15 ms (629 activities)
  * Order all activities by distance:                         15.08 ms (629 activities)
  * Order all activities by elevation gained:                 28.52 ms (629 activities)
==========================================================================

2026-08-30 23:56:49 [INFO] Running database benchmark (backend=FIREBIRD, scope=365 days)...

==========================================================================
  Kinetiqo Database Benchmark (FIREBIRD)
  Scope: Last 365 days
==========================================================================
  * Fetch all GPS data for last 365 days all activity types: 22935.50 ms (1,761,230 records)
  * Order all activities by name:                             37.25 ms (629 activities)
  * Order all activities by distance:                         34.75 ms (629 activities)
  * Order all activities by elevation gained:                 35.09 ms (629 activities)
==========================================================================