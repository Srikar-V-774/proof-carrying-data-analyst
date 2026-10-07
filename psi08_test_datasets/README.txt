PSI08 TEST DATASETS

1 sales_analytics_1000.csv: 1000 clean baseline rows.
2 messy_sales_600.csv: 608 rows with duplicates, duplicate IDs with changed values, missing values, inconsistent casing/whitespace, numeric strings, currency symbols, mixed dates, inconsistent labels, shuffled rows.
3 adversarial_multisource_800.csv: 806 rows with multiple sources, INR/USD, ambiguous dates, duplicate transaction IDs, conflicting source amounts, missing fields, suspicious negative amounts.

These are synthetic hackathon test datasets. Messy/adversarial evidence must not be silently deleted; uncertainty should be surfaced.