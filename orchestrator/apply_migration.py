import os
import psycopg2
from urllib.parse import urlparse

# Load env vars manually from flux/.env
env_path = "/Users/karanpratapsingh/Documents/GitHub/Vertex/flux/.env"
env_vars = {}
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"): continue
        k, v = line.split("=", 1)
        env_vars[k.strip()] = v.strip()

sb_pass = env_vars.get("SUPABASE_SERVICE_KEY")
db_url = f"postgresql://postgres:{sb_pass}@db.hytblxitlqnrkgsaifez.supabase.co:5432/postgres"

print("Connecting to DB...")
conn = psycopg2.connect(db_url)
conn.autocommit = True

migration_path = "/Users/karanpratapsingh/Documents/GitHub/Vertex/flux/supabase/migrations/006_flux_v2.sql"
with open(migration_path, 'r') as f:
    sql = f.read()

print("Applying migration...")
with conn.cursor() as cur:
    cur.execute(sql)

print("Migration applied successfully!")
conn.close()
