import os
from dotenv import load_dotenv
load_dotenv("../flux/.env")
from supabase_client import get_supabase
get_supabase().table("active_machines").update({"status": "closed"}).execute()
print("Cleared active machines")
