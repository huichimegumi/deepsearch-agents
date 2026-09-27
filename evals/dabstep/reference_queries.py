"""Deterministic, read-only checks used to validate the DABStep SQL import.

These queries intentionally avoid exact fee totals. The pinned snapshot does not contain a
worked fee example, and empty-list wildcard behavior needs independent validation before fee
totals can become a hard acceptance criterion.
"""

REFERENCE_QUERIES = {
    "dataset_overview": """
        SELECT
            COUNT(*) AS transaction_count,
            COUNT(DISTINCT psp_reference) AS unique_psp_references,
            COUNT(DISTINCT merchant) AS active_merchants,
            ROUND(SUM(eur_amount), 2) AS total_eur_amount,
            ROUND(AVG(eur_amount), 6) AS average_eur_amount,
            SUM(has_fraudulent_dispute) AS fraudulent_transaction_count,
            ROUND(SUM(CASE WHEN has_fraudulent_dispute = 1 THEN eur_amount ELSE 0 END), 2)
                AS fraudulent_eur_amount,
            SUM(is_refused_by_adyen) AS refused_transaction_count,
            SUM(intracountry) AS intracountry_transaction_count,
            MIN(transaction_date) AS date_min,
            MAX(transaction_date) AS date_max
        FROM payments
    """,
    "data_quality": """
        SELECT
            SUM(CASE WHEN ip_address IS NULL THEN 1 ELSE 0 END) AS missing_ip_address,
            SUM(CASE WHEN email_address IS NULL THEN 1 ELSE 0 END) AS missing_email_address,
            SUM(CASE WHEN aci NOT IN ('A','B','C','D','E','F','G') THEN 1 ELSE 0 END)
                AS invalid_aci,
            SUM(CASE WHEN m.merchant IS NULL THEN 1 ELSE 0 END) AS missing_merchant_metadata,
            SUM(CASE WHEN mcc.mcc IS NULL THEN 1 ELSE 0 END) AS missing_mcc_reference,
            SUM(
                CASE WHEN p.intracountry <>
                    CASE WHEN p.issuing_country = p.acquirer_country THEN 1 ELSE 0 END
                THEN 1 ELSE 0 END
            ) AS invalid_intracountry_derivation,
            SUM(
                CASE WHEN NOT EXISTS (
                    SELECT 1 FROM acquirer_countries a
                    WHERE a.country_code = p.acquirer_country
                ) THEN 1 ELSE 0 END
            ) AS acquirer_country_not_in_mapping
        FROM payments p
        LEFT JOIN merchants m ON m.merchant = p.merchant
        LEFT JOIN merchant_category_codes mcc ON mcc.mcc = m.merchant_category_code
    """,
    "merchant_summary": """
        SELECT
            p.merchant,
            COUNT(*) AS transaction_count,
            ROUND(SUM(p.eur_amount), 2) AS total_eur_amount,
            ROUND(AVG(p.eur_amount), 6) AS average_eur_amount,
            ROUND(100.0 * SUM(p.has_fraudulent_dispute) / COUNT(*), 6)
                AS fraudulent_transaction_pct,
            ROUND(
                100.0 * SUM(CASE WHEN p.has_fraudulent_dispute = 1 THEN p.eur_amount ELSE 0 END)
                    / SUM(p.eur_amount),
                6
            ) AS fraudulent_volume_pct,
            ROUND(100.0 * SUM(p.is_refused_by_adyen) / COUNT(*), 6) AS refusal_pct,
            ROUND(100.0 * SUM(p.intracountry) / COUNT(*), 6) AS intracountry_pct,
            m.account_type,
            m.merchant_category_code,
            m.capture_delay
        FROM payments p
        JOIN merchants m ON m.merchant = p.merchant
        GROUP BY p.merchant, m.account_type, m.merchant_category_code, m.capture_delay
        ORDER BY p.merchant
    """,
    "card_scheme_summary": """
        SELECT
            card_scheme,
            COUNT(*) AS transaction_count,
            ROUND(SUM(eur_amount), 2) AS total_eur_amount,
            ROUND(100.0 * SUM(has_fraudulent_dispute) / COUNT(*), 6)
                AS fraudulent_transaction_pct,
            ROUND(100.0 * SUM(is_refused_by_adyen) / COUNT(*), 6) AS refusal_pct
        FROM payments
        GROUP BY card_scheme
        ORDER BY card_scheme
    """,
    "routing_summary": """
        SELECT
            CASE WHEN intracountry = 1 THEN 'domestic' ELSE 'cross_border' END AS route_type,
            COUNT(*) AS transaction_count,
            ROUND(SUM(eur_amount), 2) AS total_eur_amount,
            ROUND(100.0 * SUM(has_fraudulent_dispute) / COUNT(*), 6)
                AS fraudulent_transaction_pct,
            ROUND(100.0 * SUM(is_refused_by_adyen) / COUNT(*), 6) AS refusal_pct
        FROM payments
        GROUP BY intracountry
        ORDER BY route_type
    """,
    "table_counts": """
        SELECT 'payments' AS table_name, COUNT(*) AS row_count FROM payments
        UNION ALL SELECT 'merchants', COUNT(*) FROM merchants
        UNION ALL SELECT 'merchant_acquirers', COUNT(*) FROM merchant_acquirers
        UNION ALL SELECT 'acquirer_countries', COUNT(*) FROM acquirer_countries
        UNION ALL SELECT 'merchant_category_codes', COUNT(*) FROM merchant_category_codes
        UNION ALL SELECT 'fee_rules', COUNT(*) FROM fee_rules
        UNION ALL SELECT 'fee_rule_account_types', COUNT(*) FROM fee_rule_account_types
        UNION ALL SELECT 'fee_rule_mccs', COUNT(*) FROM fee_rule_mccs
        UNION ALL SELECT 'fee_rule_acis', COUNT(*) FROM fee_rule_acis
        UNION ALL SELECT 'dataset_files', COUNT(*) FROM dataset_files
        ORDER BY table_name
    """,
}
