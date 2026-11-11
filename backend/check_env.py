import os
print(f'SESSION_SECRET: {os.getenv("SESSION_SECRET")}')
print(f'SUPABASE_URL: {os.getenv("SUPABASE_URL")}')
print(f'SUPABASE_KEY: {os.getenv("SUPABASE_KEY")}')
print(f'GROQ_API_KEY: {os.getenv("GROQ_API_KEY")}')