"""
cyber_events_embed.py

Reads a CSV of cyber news, embeds headlines via OpenAI, and stores
the headline, timestamp, and vector in a Postgres `cyber_events` table
backed by pgvector.

Expected CSV columns (names are configurable via constants below):
    headline   – article headline text
    timestamp  – ISO-8601 or any format parseable by pandas

Usage:
    python cyber_events_embed.py --csv cyber_news.csv

Dependencies:
    pip install psycopg2-binary pgvector openai pandas python-dotenv
"""

import argparse
import os
import sys

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
from pgvector.psycopg2 import register_vector

# ── Configuration ─────────────────────────────────────────────────────────────

load_dotenv()  # reads .env if present

DB_CONFIG = {
    "database_url": os.getenv("DATABASE_URL")
}
if not DB_CONFIG["database_url"]:
    sys.exit("""DATABASE_URL environment variable is not set. 
             Try Setting this in the .env file or your environment.
             Example: 'postgresql://user:password@localhost:5432/mydb'
             """)

# DB_CONFIG = {
#     "host":     os.getenv("PG_HOST", "localhost"),
#     "port":     int(os.getenv("PG_PORT", 5432)),
#     "dbname":   os.getenv("PG_DBNAME", "postgres"),
#     "user":     os.getenv("PG_USER", "postgres"),
#     "password": os.getenv("PG_PASSWORD", ""),
# }

OPENAI_MODEL    = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
EMBEDDING_DIM   = 1536          # dimensions for text-embedding-3-small
BATCH_SIZE      = 100           # headlines per OpenAI request

CSV_HEADLINE_COL   = "headline"
CSV_TIMESTAMP_COL  = "timestamp"

# ── Database helpers ──────────────────────────────────────────────────────────

DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS cyber_events (
    id          BIGSERIAL PRIMARY KEY,
    headline    TEXT        NOT NULL,
    event_time  TIMESTAMPTZ NOT NULL,
    embedding   VECTOR({EMBEDDING_DIM})
);
"""


def get_connection() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(**DB_CONFIG)
    register_vector(conn)
    return conn


def ensure_table(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    print("Table 'cyber_events' is ready.")


# ── Embedding helpers ─────────────────────────────────────────────────────────

def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Return embeddings for a list of texts (single API call)."""
    response = client.embeddings.create(model=OPENAI_MODEL, input=texts)
    return [item.embedding for item in response.data]


def embed_all(client: OpenAI, headlines: list[str]) -> list[list[float]]:
    """Embed all headlines in batches, printing progress."""
    embeddings: list[list[float]] = []
    total = len(headlines)

    for start in range(0, total, BATCH_SIZE):
        batch = headlines[start : start + BATCH_SIZE]
        embeddings.extend(embed_batch(client, batch))
        print(f"  Embedded {min(start + BATCH_SIZE, total)}/{total} headlines …")

    return embeddings


# ── Insertion ─────────────────────────────────────────────────────────────────

INSERT_SQL = """
INSERT INTO cyber_events (headline, event_time, embedding)
VALUES (%s, %s, %s)
"""


def insert_rows(
    conn: psycopg2.extensions.connection,
    headlines: list[str],
    timestamps: list[pd.Timestamp],
    embeddings: list[list[float]],
) -> None:
    rows = list(zip(headlines, timestamps, embeddings))
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, rows)
    conn.commit()
    print(f"Inserted {len(rows)} rows into cyber_events.")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed cyber news headlines into Postgres.")
    parser.add_argument("--csv", required=True, help="Path to the cyber news CSV file.")
    return parser.parse_args()


def load_csv(path: str) -> tuple[list[str], list[pd.Timestamp]]:
    df = pd.read_csv(path)

    missing = {CSV_HEADLINE_COL, CSV_TIMESTAMP_COL} - set(df.columns)
    if missing:
        sys.exit(
            f"CSV is missing required columns: {missing}\n"
            f"Found columns: {list(df.columns)}"
        )

    df = df.dropna(subset=[CSV_HEADLINE_COL, CSV_TIMESTAMP_COL]).copy()
    df[CSV_TIMESTAMP_COL] = pd.to_datetime(df[CSV_TIMESTAMP_COL], utc=True)

    headlines  = df[CSV_HEADLINE_COL].astype(str).tolist()
    timestamps = df[CSV_TIMESTAMP_COL].tolist()

    print(f"Loaded {len(headlines)} rows from '{path}'.")
    return headlines, timestamps


def main() -> None:
    args = parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY environment variable is not set.")

    headlines, timestamps = load_csv(args.csv)

    print("Connecting to Postgres …")
    conn = get_connection()
    ensure_table(conn)

    print(f"Embedding {len(headlines)} headlines via OpenAI ({OPENAI_MODEL}) …")
    client     = OpenAI(api_key=api_key)
    embeddings = embed_all(client, headlines)

    insert_rows(conn, headlines, timestamps, embeddings)
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
