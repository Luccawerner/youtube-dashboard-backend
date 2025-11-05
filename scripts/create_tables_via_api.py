"""
Criar tabelas via Supabase REST API
"""

import requests
import json

SUPABASE_URL = "https://prvkmzsteyedepvlbppyo.supabase.co"
SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBydmttenN0eWVkZXB2bGJwcHlvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NDE0NjcxNCwiZXhwIjoyMDU5NzIyNzE0fQ.w_lVUAgJO_v8q6r5Q32VQZpMSPiZhMydzpi0sMgkxho"

# Ler SQL
with open("migrations/add_analysis_tables.sql", "r", encoding="utf-8") as f:
    sql_content = f.read()

print("[*] Arquivo SQL carregado")
print(f"[*] Tamanho: {len(sql_content)} chars\n")

# Executar via PostgREST query endpoint
print("[*] Executando SQL no Supabase...")

# Supabase permite executar SQL raw via RPC se tivermos uma função
# Como não temos, vamos usar abordagem alternativa: criar via client Python

try:
    from supabase import create_client

    supabase = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

    # Separar statements individuais
    statements = [s.strip() + ";" for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]

    print(f"[*] {len(statements)} SQL statements para executar\n")

    # Executar via SQL direto (usando rpc ou postgrest)
    # Como não temos RPC, vamos criar as tabelas uma por uma via DDL

    print("[!] AVISO: Supabase Python SDK nao suporta DDL direto")
    print("[!] Voce precisa executar o SQL manualmente\n")
    print("="*60)
    print("INSTRUCOES:")
    print("="*60)
    print("1. Acesse: https://supabase.com/dashboard/project/prvkmzsteyedepvlbppyo/sql/new")
    print("2. Copie o conteudo de: migrations/add_analysis_tables.sql")
    print("3. Cole no SQL Editor")
    print("4. Clique em RUN (canto inferior direito)")
    print("="*60)

    # Vamos mostrar o SQL para facilitar
    print("\n[*] SQL a ser executado:\n")
    print(sql_content[:500])
    print("\n... (arquivo completo em migrations/add_analysis_tables.sql)")

except ImportError:
    print("[ERROR] Supabase SDK nao instalado")
    print("[*] Instalando...")
    import subprocess
    subprocess.check_call(["pip", "install", "supabase"])

except Exception as e:
    print(f"[ERROR] {str(e)}")
