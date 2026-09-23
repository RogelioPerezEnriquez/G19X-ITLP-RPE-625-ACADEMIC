import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Carga las variables de entorno desde .env
load_dotenv(".env")

url: str = os.environ.get("SUPABASE_URL")
anon_key: str = os.environ.get("SUPABASE_ANON_KEY")

if not url or not anon_key:
    raise SystemExit("❌ Faltan SUPABASE_URL o SUPABASE_ANON_KEY en .env")

# Crear cliente con anon key (el mismo que usará el frontend/agente)
supabase: Client = create_client(url, anon_key)

print("🔍 Probando INSERT con anon key (debe fallar por RLS)...")

try:
    response = supabase.table("productos").insert({
        "nombre": "test_rls_producto",
        "categoria": "prueba",
        "costo_unitario": 10,
        "stock_actual": 0,
        "costo_ordenar": 5,
        "costo_mantener_pct_anual": 20
    }).execute()

    # Si llega aquí, RLS NO está bloqueando
    print("❌ FALLO DE SEGURIDAD: El INSERT se ejecutó. RLS no está bien aplicado.")
    print(f"   Respuesta: {response}")
    print("   Revisa que las políticas de RLS estén activas y que NO haya policy de INSERT para anon.")

except Exception as e:
    error_msg = str(e).lower()
    if "row-level security" in error_msg or "rls" in error_msg or "42501" in error_msg:
        print("✅ CORRECTO: RLS bloqueó el INSERT con anon key.")
        print(f"   Error esperado: {e}")
    else:
        print(f"⚠️ Falló el INSERT, pero con otro error. Revísalo:")
        print(f"   {e}")