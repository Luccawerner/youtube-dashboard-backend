"""
Script para executar migration SQL no Supabase via PostgreSQL
"""

import sys
import psycopg2

def execute_migration():
    """Executa o SQL usando psycopg2"""

    # Credenciais PostgreSQL do Supabase
    DB_HOST = "db.prvkmzsteyedepvlbppyo.supabase.co"
    DB_NAME = "postgres"
    DB_USER = "postgres.prvkmzsteyedepvlbppyo"
    DB_PORT = "5432"
    DB_PASSWORD = "pgRW4Nv2E37P98XA"

    # Ler SQL
    sql_file = "migrations/add_analysis_tables.sql"
    print(f"[*] Lendo {sql_file}...")

    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    print("[*] Conectando ao PostgreSQL...")

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            connect_timeout=10
        )

        cursor = conn.cursor()
        print("[OK] Conectado com sucesso!\n")

        # Executar SQL completo
        print("[*] Executando migration...")
        cursor.execute(sql_content)
        conn.commit()

        print("[OK] Migration executada com sucesso!\n")

        # Verificar tabelas criadas
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('keyword_analysis', 'title_patterns', 'top_channels_snapshot', 'gap_analysis', 'weekly_reports')
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()

        print("[*] Tabelas criadas:")
        for table in tables:
            print(f"   [OK] {table[0]}")

        cursor.close()
        conn.close()

        print("\n[SUCCESS] Migration completa!")

    except psycopg2.OperationalError as e:
        print(f"[ERROR] Erro de conexao: {str(e)}")
        sys.exit(1)

    except Exception as e:
        print(f"[ERROR] Erro ao executar SQL: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    execute_migration()
