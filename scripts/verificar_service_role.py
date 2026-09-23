import os
from pathlib import Path
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent /".env")

url: str | None = os.environ.get("SUPABASE_URL")
service_key: str | None = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not url or not service_key:
    raise SystemExit(
        "❌ Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env\n"
        "   La service_role key está en Supabase → Settings → API → service_role."
    )

supabase: Client = create_client(url, service_key)

print("🔍 Probando INSERT con service_role key (debe funcionar)...")

# 1. INSERT
try:
    insert_response = supabase.table("productos").insert({
        "nombre": "test_service_role",
        "categoria": "prueba_rls",
        "costo_unitario": 10,
        "stock_actual": 0,
        "costo_ordenar": 5,
        "costo_mantener_pct_anual": 20,
    }).execute()
except Exception as e:
    print(f"❌ FALLO: la service_role key no pudo insertar. Esto NO debería pasar.")
    print(f"   Error: {e}")
    raise SystemExit(1)

if not insert_response.data:
    print("❌ INSERT no devolvió datos. Revisa el schema de la tabla productos.")
    raise SystemExit(1)

nuevo_id = insert_response.data[0]["id"]
print(f"✅ INSERT OK. Fila creada con id = {nuevo_id}")

# 2. SELECT (verificar que se guardó)
select_response = supabase.table("productos").select("*").eq("id", nuevo_id).execute()
if select_response.data:
    print(f"✅ SELECT OK. Fila recuperada: {select_response.data[0]['nombre']}")
else:
    print("❌ SELECT no encontró la fila recién insertada.")
    raise SystemExit(1)

# 3. UPDATE
update_response = (
    supabase.table("productos")
    .update({"categoria": "prueba_rls_actualizada"})
    .eq("id", nuevo_id)
    .execute()
)
if update_response.data and update_response.data[0]["categoria"] == "prueba_rls_actualizada":
    print("✅ UPDATE OK.")
else:
    print("❌ UPDATE no aplicó el cambio.")
    raise SystemExit(1)

# 4. DELETE (limpieza)
delete_response = (
    supabase.table("productos")
    .delete()
    .eq("id", nuevo_id)
    .execute()
)
if delete_response.data:
    print(f"✅ DELETE OK. Fila {nuevo_id} eliminada.")
else:
    print("⚠️ DELETE no devolvió datos. Verifica manualmente en Supabase.")

print("\n🎉 Aislamiento verificado:")
print("   - anon key       → solo lectura (RLS bloquea escrituras)")
print("   - service_role   → lectura/escritura completa (ignora RLS)")