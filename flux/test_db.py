import asyncio
import os
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")

supabase = create_client(url, key)

result = supabase.table("transactions").select("company_id").limit(2).execute()
print("company_ids:", [r['company_id'] for r in result.data])
