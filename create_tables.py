#!/usr/bin/env python3
"""Crear tablas Supabase para CLIPSO.AI"""
import sys
import os
import psycopg2
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Uso: python create_tables.py <postgres_password>")
        sys.exit(1)

    password = sys.argv[1]

    try:
        conn = psycopg2.connect(
            host="db.wrxavfgydefiprfzwnra.supabase.co",
            database="postgres",
            user="postgres",
            password=password,
            port=5432,
            sslmode="require"
        )

        cursor = conn.cursor()

        schema_path = Path(__file__).parent / "supabase_schema.sql"
        with open(schema_path, "r") as f:
            sql = f.read()

        print("📝 Ejecutando schema SQL...")
        cursor.execute(sql)
        conn.commit()

        cursor.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename LIKE 'clipso_%'
        """)

        tables = cursor.fetchall()
        print(f"✅ Tablas creadas: {[t[0] for t in tables]}")

        cursor.close()
        conn.close()

    except psycopg2.OperationalError as e:
        print(f"❌ Error de conexión: {e}")
        print("Verifica que la contraseña sea correcta")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
