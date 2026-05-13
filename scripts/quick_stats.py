#!/usr/bin/env python3
"""Quick stats query using direct PostgreSQL connection (faster than Supabase client)."""

import os
import psycopg2
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

# Direct PostgreSQL connection (bypasses Supabase REST API)
password = quote_plus(os.getenv("DATABASE_PASSWORD"))
conn_string = f"postgresql://postgres:{password}@db.zwcreraudeemddmloeul.supabase.co:5432/postgres"

conn = psycopg2.connect(conn_string)
cur = conn.cursor()

print("=" * 60)
print("PI COVERAGE STATS")
print("=" * 60)

cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE avoid_search = false) as with_pi,
        COUNT(*) FILTER (WHERE avoid_search = true) as without_pi
    FROM trials
""")
total, with_pi, without_pi = cur.fetchone()
print(f"Total trials: {total:,}")
print(f"With PI (avoid_search=false): {with_pi:,} ({100*with_pi/total:.1f}%)")
print(f"Without PI (avoid_search=true): {without_pi:,} ({100*without_pi/total:.1f}%)")

print()
print("=" * 60)
print("ONCOLOGY TRIALS (searching conditions array)")
print("=" * 60)

# Use array search which is faster
cur.execute("""
    SELECT COUNT(*) FROM trials 
    WHERE conditions::text ILIKE '%cancer%'
       OR conditions::text ILIKE '%tumor%'
       OR conditions::text ILIKE '%carcinoma%'
       OR conditions::text ILIKE '%lymphoma%'
       OR conditions::text ILIKE '%leukemia%'
       OR conditions::text ILIKE '%melanoma%'
""")
oncology = cur.fetchone()[0]
print(f"Oncology-related trials: {oncology:,}")

# With PI vs without
cur.execute("""
    SELECT 
        COUNT(*) FILTER (WHERE avoid_search = false) as with_pi,
        COUNT(*) FILTER (WHERE avoid_search = true) as without_pi
    FROM trials 
    WHERE conditions::text ILIKE '%cancer%'
       OR conditions::text ILIKE '%tumor%'
       OR conditions::text ILIKE '%carcinoma%'
       OR conditions::text ILIKE '%lymphoma%'
       OR conditions::text ILIKE '%leukemia%'
       OR conditions::text ILIKE '%melanoma%'
""")
onc_with_pi, onc_without_pi = cur.fetchone()
print(f"  With PI: {onc_with_pi:,}")
print(f"  Without PI: {onc_without_pi:,}")

print()
print("=" * 60)
print("OBESITY/DIABETES TRIALS")
print("=" * 60)

cur.execute("""
    SELECT COUNT(*) FROM trials 
    WHERE conditions::text ILIKE '%obesity%'
       OR conditions::text ILIKE '%diabetes%'
       OR conditions::text ILIKE '%weight loss%'
       OR conditions::text ILIKE '%overweight%'
       OR brief_title ILIKE '%semaglutide%'
       OR brief_title ILIKE '%GLP-1%'
""")
obesity_diabetes = cur.fetchone()[0]
print(f"Obesity/Diabetes-related trials: {obesity_diabetes:,}")

cur.execute("""
    SELECT 
        COUNT(*) FILTER (WHERE avoid_search = false) as with_pi,
        COUNT(*) FILTER (WHERE avoid_search = true) as without_pi
    FROM trials 
    WHERE conditions::text ILIKE '%obesity%'
       OR conditions::text ILIKE '%diabetes%'
       OR conditions::text ILIKE '%weight loss%'
       OR conditions::text ILIKE '%overweight%'
       OR brief_title ILIKE '%semaglutide%'
       OR brief_title ILIKE '%GLP-1%'
""")
ob_with_pi, ob_without_pi = cur.fetchone()
print(f"  With PI: {ob_with_pi:,}")
print(f"  Without PI: {ob_without_pi:,}")

cur.close()
conn.close()
