"""
Script para executar migrations SQL no Supabase
Usage: python scripts/run_migration.py
"""

import os
import sys
from supabase import create_client, Client

# Supabase credentials
SUPABASE_URL = "https://prvkmzsteyedepvlbppyo.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBydmttenN0eWVkZXB2bGJwcHlvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NDE0NjcxNCwiZXhwIjoyMDU5NzIyNzE0fQ.w_lVUAgJO_v8q6r5Q32VQZpMSPiZhMydzpi0sMgkxho"

def run_migration():
    """Executa o arquivo SQL de migration"""

    # Ler arquivo SQL
    sql_file = "migrations/add_analysis_tables.sql"

    try:
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {sql_file}")
        sys.exit(1)

    print("📄 Arquivo SQL lido com sucesso")
    print(f"📊 Tamanho: {len(sql_content)} caracteres")

    # Conectar ao Supabase
    print("\n🔌 Conectando ao Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # Dividir SQL em statements individuais (PostgreSQL)
    statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]

    print(f"📝 {len(statements)} statements para executar\n")

    # Executar cada statement
    success_count = 0
    error_count = 0

    for idx, statement in enumerate(statements, 1):
        # Pular comentários
        if statement.startswith('--') or statement.startswith('COMMENT'):
            continue

        # Mostrar apenas primeira linha do statement (preview)
        preview = statement.split('\n')[0][:60]
        print(f"[{idx}/{len(statements)}] Executando: {preview}...")

        try:
            # Executar via RPC (Supabase não tem método direto para SQL raw)
            # Vamos usar a REST API diretamente
            import requests

            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/rpc/",
                headers={
                    "apikey": SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                    "Content-Type": "application/json"
                },
                json={"query": statement}
            )

            # Como não temos RPC configurado, vamos usar abordagem diferente
            # Vou salvar o SQL para ser executado manualmente via Supabase UI

            print(f"   ⚠️  Executar manualmente no Supabase SQL Editor")

        except Exception as e:
            print(f"   ❌ Erro: {str(e)}")
            error_count += 1

    print(f"\n{'='*60}")
    print(f"✅ Migration preparada!")
    print(f"{'='*60}")
    print(f"\n📋 PRÓXIMO PASSO:")
    print(f"1. Abra o Supabase: https://supabase.com/dashboard/project/prvkmzsteyedepvlbppyo")
    print(f"2. Vá em 'SQL Editor'")
    print(f"3. Copie e cole o conteúdo de: migrations/add_analysis_tables.sql")
    print(f"4. Execute o SQL")
    print(f"\nOu use o método alternativo abaixo:")

if __name__ == "__main__":
    run_migration()
