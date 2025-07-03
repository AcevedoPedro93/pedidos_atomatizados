import streamlit as st
import pandas as pd
import numpy as np
from io import StringIO
import pyperclip  # para acceder al portapapeles

st.title("🛒 Calculadora de Pedido (ready-to-copy)")

# — Botones: Limpiar, Pegar desde portapapeles, Calcular —
col1, col2, col3, _ = st.columns([1,1,1,6])
with col1:
    def clear_inputs():
        st.session_state.pop('text_input', None)
    st.button("🔄 Limpiar todo", on_click=clear_inputs)
with col2:
    def paste_from_clipboard():
        try:
            st.session_state['text_input'] = pyperclip.paste()
        except Exception:
            st.error("No se pudo leer el portapapeles.")
    st.button("📋 Pegar", on_click=paste_from_clipboard)
with col3:
    calc = st.button("📊 Calcular pedido")

placeholder = st.empty()

# — Entrada de texto y días —
txt = st.text_area(
    "Pega aquí tu tabla cruda (encabezados; separa columnas por espacios/tab):",
    value=st.session_state.get('text_input',''),
    key='text_input',
    height=200
)
days = st.number_input("Multiplicador de días para stock:", value=3, min_value=1, key='days')

if not calc:
    st.info("Pulsa '📊 Calcular pedido' para ejecutar los cálculos.")
    st.stop()
if not txt.strip():
    st.error("No hay datos. Pega la tabla en el área de texto.")
    st.stop()

# — Leer y normalizar —
try:
    df = pd.read_csv(StringIO(txt), delim_whitespace=True)
except Exception as e:
    st.error(f"Error al parsear: {e}")
    st.stop()
df.columns = df.columns.astype(str).str.strip().str.replace(r"\.","",regex=True)

# — Identificar sucursal y parsear columnas numéricas —
suc_col = [c for c in df.columns if c.lower().startswith('suc')][0]
df[suc_col] = df[suc_col].astype(str).str.zfill(4)
for c in df.columns:
    if c == suc_col: 
        continue
    df[c] = (
        df[c].astype(str)
             .str.replace(r"[\/\|].*","", regex=True)
             .replace('', '0')
             .astype(int)
    )

# — Guardar existencias originales y clip para cálculos —
df['Exi_raw'] = df['Exi']
df['Exi']     = df['Exi'].clip(lower=0)

# — Validar columnas requeridas —
for col in ['V30D','V60D','Exi','VF','1T','2T','3T','4T']:
    if col not in df.columns:
        st.error(f"Falta columna '{col}'")
        st.stop()

# — Filtrar sucursales activas y bodegas —
active     = [f"{i:04d}" for i in range(1,28) if i not in (10,20)]
warehouses = ['0100','0105','0106']
df_act     = df[df[suc_col].isin(active)].copy()

# — Máscaras para lógica de `VF` vs `Ts` —
mask_vf_zero_ts = (df_act['VF']>0) & (df_act[['1T','2T','3T','4T']].sum(axis=1)==0)
mask_vf_ts      = (df_act['VF']>0) & ~mask_vf_zero_ts
mask_no_vf      = df_act['VF']==0

# — Calcular `Prom` según condiciones solicitadas —
df_act['Prom'] = 0.0

# 1) VF>0 y sin Ts → 1
df_act.loc[mask_vf_zero_ts, 'Prom'] = 1

# 2) VF>0 y con Ts → promedio de las Ts (sin multiplicar por días), mínimo 1
base_ts = df_act.loc[mask_vf_ts, ['1T','2T','3T','4T']].mean(axis=1)
df_act.loc[mask_vf_ts, 'Prom'] = base_ts.where(base_ts >= 1, 1)

# 3) VF=0 → ceil((V30D+V60D)/2) * days
df_act.loc[mask_no_vf, 'Prom'] = (
    np.ceil((df_act.loc[mask_no_vf,'V30D'] + df_act.loc[mask_no_vf,'V60D']) / 2)
    * days
)

# — Calcular pedido y filtrar sucursales con pedido > 0 —
df_act['Pedido'] = (df_act['Prom'] - df_act['Exi']).clip(lower=0).round().astype(int)
df_req = (
    df_act[df_act['Pedido'] > 0]
    [[suc_col, 'Pedido']]
    .rename(columns={suc_col: 'Sucursal', 'Pedido': 'Cantidad'})
)

# — Total neto —
stock_wh  = int(df[df[suc_col].isin(warehouses)]['Exi'].sum())
total_net = max(0, df_act['Pedido'].sum() - stock_wh)
placeholder.markdown(f"### Total neto a pedir: {total_net}")

# — Mostrar tabla de pedidos —
st.write("**Sucursales con pedido (>0):**")
st.dataframe(df_req.reset_index(drop=True))

# — Inventario en bodegas coloreado —
st.write("**Inventario en bodegas (0100, 0105, 0106):**")
df_wh = (
    df[df[suc_col].isin(warehouses)]
    [[suc_col, 'Exi_raw']]
    .rename(columns={suc_col: 'Sucursal', 'Exi_raw': 'Existencias'})
)

html_wh = """
<table style="border-collapse:collapse; width:100%;">
  <tr style="background:#333; color:#fff;">
    <th style="border:1px solid #555; padding:4px; text-align:left;">Sucursal</th>
    <th style="border:1px solid #555; padding:4px; text-align:right;">Existencias</th>
  </tr>
"""
for _, row in df_wh.iterrows():
    e = row['Existencias']
    bg = "#669966" if e > 0 else ("#996666" if e < 0 else "transparent")
    html_wh += f"""
  <tr style="background:{bg};">
    <td style="border:1px solid #ddd; padding:4px;">{row['Sucursal']}</td>
    <td style="border:1px solid #ddd; padding:4px; text-align:right;">{e}</td>
  </tr>
"""
html_wh += "</table>"

st.markdown(html_wh, unsafe_allow_html=True)
