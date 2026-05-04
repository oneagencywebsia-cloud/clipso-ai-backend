# Script para crear tablas en Supabase con contraseña segura
$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$password = Read-Host -AsSecureString -Prompt "Contraseña PostgreSQL"

# Convertir SecureString a texto plano
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($password)
$unsecurePassword = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($bstr)

# Instalar psycopg2 si no está presente
pip install psycopg2-binary 2>&1 | Out-Null

# Ejecutar script Python
& python ("$projectPath\create_tables.py") $unsecurePassword

# Limpiar
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
