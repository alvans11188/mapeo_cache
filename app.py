import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import math
from dataclasses import dataclass, field
from typing import List, Optional
import time

# ══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN DE PÁGINA
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Simulador de Caché",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════
#  ESTILOS CSS
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
    /* Fondo general */
    .stApp { background-color: #0e1117; }

    /* Tarjetas de métricas */
    .metric-card {
        background: linear-gradient(135deg, #1e2130, #252a3a);
        border: 1px solid #2e3a5c;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin: 6px 0;
    }
    .metric-card .label {
        color: #8899bb;
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
        margin-bottom: 6px;
    }
    .metric-card .value {
        color: #e8eaf6;
        font-size: 32px;
        font-weight: 700;
    }
    .metric-card .sub {
        color: #556688;
        font-size: 12px;
        margin-top: 4px;
    }

    /* HIT badge */
    .badge-hit {
        background: #1b4332;
        color: #40d98e;
        padding: 3px 12px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 700;
        border: 1px solid #40d98e;
    }
    /* MISS badge */
    .badge-miss {
        background: #4a1a1a;
        color: #f87171;
        padding: 3px 12px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 700;
        border: 1px solid #f87171;
    }

    /* Tabla de accesos */
    .access-table {
        background: #1a1f2e;
        border-radius: 10px;
        padding: 4px;
        border: 1px solid #2a3050;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #131720;
        border-right: 1px solid #1e2a40;
    }

    /* Título principal */
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #60a5fa, #a78bfa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2px;
    }
    .main-sub {
        color: #556688;
        font-size: 14px;
        margin-bottom: 20px;
    }

    /* Sección de bits */
    .bits-box {
        background: #12192a;
        border: 1px solid #1e3a5f;
        border-radius: 8px;
        padding: 14px 18px;
        font-family: 'Courier New', monospace;
        font-size: 13px;
        color: #7dd3fc;
    }

    /* Estado de caché visual */
    .cache-set-header {
        background: #1e2a40;
        border-radius: 6px 6px 0 0;
        padding: 6px 12px;
        font-size: 12px;
        color: #60a5fa;
        font-weight: 700;
        letter-spacing: 1px;
    }
    .cache-line-valid {
        background: #0d2137;
        border-left: 3px solid #3b82f6;
        padding: 5px 12px;
        font-family: monospace;
        font-size: 12px;
        color: #93c5fd;
        margin: 1px 0;
    }
    .cache-line-empty {
        background: #111520;
        border-left: 3px solid #1e293b;
        padding: 5px 12px;
        font-family: monospace;
        font-size: 12px;
        color: #2e3a50;
        margin: 1px 0;
    }

    /* Separador */
    hr { border-color: #1e2a40 !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  LÓGICA DEL SIMULADOR (traducida del C++)
# ══════════════════════════════════════════════════════════════

@dataclass
class CacheLine:
    valid: bool = False
    dirty: bool = False
    tag: int = 0
    last_used: int = 0
    frequency: int = 0

@dataclass
class AccessResult:
    block:      int
    address:    int
    index:      int
    tag:        int
    set_dest:   int
    result:     str       # "Hit" | "Miss"
    miss_type:  str       # "Compulsorio" | "Conflicto/Cap" | ""
    index_bin:  str
    tag_bin:    str
    offset_bin: str
    policy:     str
    evicted_tag: Optional[int] = None

class CacheSimulator:
    def __init__(self, cache_size: int, block_size: int, associativity: int, policy: str):
        if not self._is_pow2(cache_size) or not self._is_pow2(block_size):
            raise ValueError("El tamaño de caché y bloque deben ser potencias de 2.")

        self.cache_size    = cache_size
        self.block_size    = block_size
        self.associativity = associativity
        self.policy        = policy  # "LRU" | "LFU" | "FIFO" | "Random"

        self.num_sets     = cache_size // (block_size * associativity)
        self.offset_bits  = self._log2(block_size)
        self.index_bits   = self._log2(self.num_sets) if self.num_sets > 1 else 0
        self.tag_bits     = 32 - (self.index_bits + self.offset_bits)

        # Inicializar sets (lista de listas de CacheLine)
        self.sets: List[List[CacheLine]] = [
            [CacheLine() for _ in range(associativity)]
            for _ in range(self.num_sets)
        ]

        self.hits                    = 0
        self.misses                  = 0
        self.compulsory_misses       = 0
        self.conflict_capacity_misses= 0
        self.global_time             = 0
        self.access_log: List[AccessResult] = []

    @staticmethod
    def _is_pow2(x: int) -> bool:
        return x > 0 and (x & (x - 1)) == 0

    @staticmethod
    def _log2(x: int) -> int:
        return int(math.log2(x)) if x > 1 else 0

    @staticmethod
    def _to_bin(val: int, bits: int) -> str:
        if bits == 0:
            return "0"
        return format(val, f'0{bits}b')

    def _find_victim(self, lines: List[CacheLine]) -> int:
        # Primero buscar línea inválida
        for i, line in enumerate(lines):
            if not line.valid:
                return i

        if self.policy == "LRU":
            return min(range(len(lines)), key=lambda i: lines[i].last_used)
        elif self.policy == "LFU":
            return min(range(len(lines)), key=lambda i: lines[i].frequency)
        elif self.policy == "FIFO":
            return min(range(len(lines)), key=lambda i: lines[i].last_used)
        elif self.policy == "Random":
            import random
            return random.randint(0, len(lines) - 1)
        return 0

    def access(self, req_block: int) -> AccessResult:
        address     = req_block * self.block_size
        self.global_time += 1
        curr_time   = self.global_time

        offset_mask = (1 << self.offset_bits) - 1
        index_mask  = (1 << self.index_bits) - 1 if self.index_bits > 0 else 0

        offset  = address & offset_mask
        index   = (address >> self.offset_bits) & index_mask if self.index_bits > 0 else 0
        tag     = address >> (self.offset_bits + self.index_bits)

        curr_set = self.sets[index]
        hit = False

        for line in curr_set:
            if line.valid and line.tag == tag:
                hit = True
                line.last_used = curr_time
                line.frequency += 1
                self.hits += 1
                break

        evicted_tag = None
        miss_type   = ""

        if not hit:
            self.misses += 1
            victim_idx = self._find_victim(curr_set)

            if not curr_set[victim_idx].valid:
                self.compulsory_misses += 1
                miss_type = "Compulsorio"
            else:
                self.conflict_capacity_misses += 1
                miss_type = "Conflicto/Cap"
                evicted_tag = curr_set[victim_idx].tag

            curr_set[victim_idx].valid     = True
            curr_set[victim_idx].tag       = tag
            curr_set[victim_idx].last_used = curr_time
            curr_set[victim_idx].frequency = 1

        result = AccessResult(
            block      = req_block,
            address    = address,
            index      = index,
            tag        = tag,
            set_dest   = index,
            result     = "Hit" if hit else "Miss",
            miss_type  = miss_type,
            index_bin  = self._to_bin(index, self.index_bits),
            tag_bin    = self._to_bin(tag, self.tag_bits),
            offset_bin = self._to_bin(offset, self.offset_bits),
            policy     = self.policy,
            evicted_tag= evicted_tag,
        )
        self.access_log.append(result)
        return result

    def get_stats(self) -> dict:
        total = self.hits + self.misses
        hit_rate  = self.hits  / total if total > 0 else 0
        miss_rate = self.misses / total if total > 0 else 0
        amat = 1.0 + (miss_rate * 100.0)
        return {
            "total":       total,
            "hits":        self.hits,
            "misses":      self.misses,
            "hit_rate":    hit_rate,
            "miss_rate":   miss_rate,
            "compulsory":  self.compulsory_misses,
            "conflict":    self.conflict_capacity_misses,
            "amat":        amat,
            "num_sets":    self.num_sets,
            "offset_bits": self.offset_bits,
            "index_bits":  self.index_bits,
            "tag_bits":    self.tag_bits,
        }

    def reset(self):
        self.__init__(self.cache_size, self.block_size, self.associativity, self.policy)

# ══════════════════════════════════════════════════════════════
#  HELPERS DE VISUALIZACIÓN
# ══════════════════════════════════════════════════════════════

def metric_card(label: str, value: str, sub: str = ""):
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    st.markdown(f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {sub_html}
    </div>
    """, unsafe_allow_html=True)

def hit_badge(result: str) -> str:
    cls = "badge-hit" if result == "Hit" else "badge-miss"
    return f'<span class="{cls}">{result}</span>'

def gauge_chart(value: float, title: str, color: str) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=round(value * 100, 1),
        number={"suffix": "%", "font": {"size": 28, "color": "#e8eaf6"}},
        title={"text": title, "font": {"size": 14, "color": "#8899bb"}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#556688",
                     "tickfont": {"color": "#556688"}},
            "bar": {"color": color},
            "bgcolor": "#1a1f2e",
            "bordercolor": "#2a3050",
            "steps": [
                {"range": [0,  50], "color": "#1a1f2e"},
                {"range": [50, 75], "color": "#1e2540"},
                {"range": [75,100], "color": "#1e2f50"},
            ],
        }
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor ="rgba(0,0,0,0)",
        height=200,
        margin=dict(t=40, b=10, l=20, r=20),
    )
    return fig

def history_chart(log: List[AccessResult]) -> go.Figure:
    hits_acc   = []
    misses_acc = []
    h = m = 0
    for r in log:
        if r.result == "Hit": h += 1
        else: m += 1
        hits_acc.append(h)
        misses_acc.append(m)

    x = list(range(1, len(log) + 1))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=hits_acc, name="Hits acumulados",
        line=dict(color="#40d98e", width=2), fill="tozeroy",
        fillcolor="rgba(64,217,142,0.08)"))
    fig.add_trace(go.Scatter(x=x, y=misses_acc, name="Misses acumulados",
        line=dict(color="#f87171", width=2), fill="tozeroy",
        fillcolor="rgba(248,113,113,0.08)"))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor ="rgba(14,17,23,0.8)",
        font=dict(color="#8899bb"),
        xaxis=dict(title="Acceso #", gridcolor="#1e2a40", color="#556688"),
        yaxis=dict(title="Cantidad",  gridcolor="#1e2a40", color="#556688"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#aabbcc")),
        margin=dict(t=10, b=40, l=40, r=20),
        height=260,
    )
    return fig

def miss_pie(compulsory: int, conflict: int) -> go.Figure:
    if compulsory + conflict == 0:
        return None
    fig = go.Figure(go.Pie(
        labels=["Compulsorios", "Conflicto/Cap"],
        values=[compulsory, conflict],
        hole=0.55,
        marker=dict(colors=["#f59e0b", "#f87171"],
                    line=dict(color="#0e1117", width=2)),
        textfont=dict(color="#e8eaf6"),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8899bb"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#aabbcc")),
        margin=dict(t=10, b=10, l=10, r=10),
        height=230,
        showlegend=True,
    )
    return fig

def render_cache_state(sim: CacheSimulator, max_sets: int = 16):
    sets_to_show = min(sim.num_sets, max_sets)
    cols = st.columns(min(sets_to_show, 4))
    for s_idx in range(sets_to_show):
        with cols[s_idx % 4]:
            st.markdown(f'<div class="cache-set-header">SET {s_idx}</div>',
                        unsafe_allow_html=True)
            for way, line in enumerate(sim.sets[s_idx]):
                if line.valid:
                    st.markdown(
                        f'<div class="cache-line-valid">'
                        f'[W{way}] TAG={line.tag} | LU={line.last_used} | F={line.frequency}'
                        f'</div>', unsafe_allow_html=True)
                else:
                    st.markdown(
                        f'<div class="cache-line-empty">[W{way}] — vacío —</div>',
                        unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  ESTADO DE SESIÓN
# ══════════════════════════════════════════════════════════════
if "sim"        not in st.session_state: st.session_state.sim        = None
if "log_df"     not in st.session_state: st.session_state.log_df     = pd.DataFrame()
if "configured" not in st.session_state: st.session_state.configured = False

# ══════════════════════════════════════════════════════════════
#  SIDEBAR — CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Configuración de Caché")
    st.markdown("---")

    cache_size = st.selectbox(
        "Tamaño total de caché (bytes)",
        [64, 128, 256, 512, 1024, 2048, 4096],
        index=2,
        help="Debe ser potencia de 2"
    )
    block_size = st.selectbox(
        "Tamaño de bloque (bytes)",
        [8, 16, 32, 64, 128],
        index=2,
        help="Debe ser potencia de 2"
    )
    assoc_map = {
        "Mapeo Directo (1-way)": 1,
        "2-way Asociativo":       2,
        "4-way Asociativo":       4,
        "8-way Asociativo":       8,
        "Totalmente Asociativo":  cache_size // block_size,
    }
    assoc_label = st.selectbox("Asociatividad", list(assoc_map.keys()), index=0)
    associativity = assoc_map[assoc_label]

    policy = st.radio(
        "Política de reemplazo",
        ["LRU", "LFU", "FIFO", "Random"],
        index=0,
        horizontal=False,
    )

    # Preview de bits
    try:
        ns  = cache_size // (block_size * associativity)
        ob  = int(math.log2(block_size))
        ib  = int(math.log2(ns)) if ns > 1 else 0
        tb  = 32 - (ib + ob)
        st.markdown("---")
        st.markdown("**Vista previa de bits de dirección (32-bit)**")
        st.markdown(f"""
        <div class="bits-box">
        📌 Sets     : {ns}<br>
        🏷️  TAG      : {tb} bits<br>
        📍 INDEX    : {ib} bits<br>
        📦 OFFSET   : {ob} bits
        </div>
        """, unsafe_allow_html=True)
    except:
        pass

    st.markdown("---")
    if st.button("🚀 Inicializar / Reiniciar Caché", use_container_width=True, type="primary"):
        try:
            st.session_state.sim = CacheSimulator(cache_size, block_size, associativity, policy)
            st.session_state.log_df = pd.DataFrame()
            st.session_state.configured = True
            st.success("✅ Caché inicializada correctamente")
        except ValueError as e:
            st.error(str(e))

# ══════════════════════════════════════════════════════════════
#  CONTENIDO PRINCIPAL
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="main-title">🧠 Simulador de Caché CPU</div>', unsafe_allow_html=True)
st.markdown('<div class="main-sub">Visualización interactiva · Mapeo directo · Asociativo · LRU / LFU / FIFO / Random</div>',
            unsafe_allow_html=True)

if not st.session_state.configured or st.session_state.sim is None:
    st.info("👈 Configura los parámetros en la barra lateral y presiona **Inicializar Caché**")
    st.stop()

sim: CacheSimulator = st.session_state.sim

# ── PESTAÑAS ─────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(
    ["🎯 Simular Accesos", "📊 Estadísticas", "🗂️ Estado de Caché", "📖 Historial"]
)

# ══════════════════════════════════════════════════════════════
#  TAB 1 — SIMULAR ACCESOS
# ══════════════════════════════════════════════════════════════
with tab1:
    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.markdown("### Acceso manual a bloques")
        manual_input = st.text_input(
            "Bloques a acceder (separados por espacios o comas)",
            placeholder="ej: 0 1 2 3 2 1 0 5",
            key="manual_blocks"
        )
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            run_manual = st.button("▶️ Ejecutar accesos", use_container_width=True, type="primary")
        with col_btn2:
            clear_btn = st.button("🗑️ Limpiar log", use_container_width=True)

        if clear_btn:
            st.session_state.sim = CacheSimulator(
                sim.cache_size, sim.block_size, sim.associativity, sim.policy)
            st.session_state.log_df = pd.DataFrame()
            st.rerun()

        if run_manual and manual_input.strip():
            try:
                raw = manual_input.replace(",", " ").split()
                blocks = [int(x) for x in raw]
                new_rows = []
                for b in blocks:
                    r = st.session_state.sim.access(b)
                    new_rows.append({
                        "#":         len(st.session_state.log_df) + len(new_rows) + 1,
                        "Bloque":    r.block,
                        "Dirección": f"0x{r.address:04X}",
                        "TAG (bin)": r.tag_bin,
                        "IDX (bin)": r.index_bin,
                        "OFF (bin)": r.offset_bin,
                        "Set":       r.set_dest,
                        "Resultado": r.result,
                        "Tipo Miss": r.miss_type,
                    })
                new_df = pd.DataFrame(new_rows)
                st.session_state.log_df = pd.concat(
                    [st.session_state.log_df, new_df], ignore_index=True)
                st.success(f"✅ {len(blocks)} acceso(s) procesado(s)")
            except ValueError:
                st.error("Solo ingresa números enteros separados por espacios o comas.")

    with col_right:
        st.markdown("### Patrones de acceso predefinidos")

        pattern = st.selectbox("Selecciona un patrón", [
            "Secuencial (0 → N)",
            "Acceso repetido (temporal locality)",
            "Stride-2 (0, 2, 4, 6...)",
            "Aleatorio",
            "Thrashing (peor caso)",
            "Personalizado",
        ])

        n_refs = st.slider("Número de referencias", 4, 64, 16)

        custom_pat = ""
        if pattern == "Personalizado":
            custom_pat = st.text_input("Secuencia personalizada", "0 1 2 0 1 2 3 0")

        if st.button("▶️ Ejecutar patrón", use_container_width=True):
            import random as rnd
            ns = sim.num_sets

            if pattern == "Secuencial (0 → N)":
                blocks = list(range(n_refs))
            elif pattern == "Acceso repetido (temporal locality)":
                base = list(range(min(4, ns)))
                blocks = (base * (n_refs // len(base) + 1))[:n_refs]
            elif pattern == "Stride-2 (0, 2, 4, 6...)":
                blocks = [i * 2 for i in range(n_refs)]
            elif pattern == "Aleatorio":
                blocks = [rnd.randint(0, ns * 4) for _ in range(n_refs)]
            elif pattern == "Thrashing (peor caso)":
                # Accede a ns+1 bloques que mapean al mismo set → thrashing
                blocks = [(i * ns) % (ns * sim.associativity + 1) for i in range(n_refs)]
            else:
                try:
                    blocks = [int(x) for x in custom_pat.replace(",", " ").split()]
                except:
                    st.error("Formato inválido")
                    blocks = []

            if blocks:
                new_rows = []
                for b in blocks:
                    r = st.session_state.sim.access(b)
                    new_rows.append({
                        "#":         len(st.session_state.log_df) + len(new_rows) + 1,
                        "Bloque":    r.block,
                        "Dirección": f"0x{r.address:04X}",
                        "TAG (bin)": r.tag_bin,
                        "IDX (bin)": r.index_bin,
                        "OFF (bin)": r.offset_bin,
                        "Set":       r.set_dest,
                        "Resultado": r.result,
                        "Tipo Miss": r.miss_type,
                    })
                new_df = pd.DataFrame(new_rows)
                st.session_state.log_df = pd.concat(
                    [st.session_state.log_df, new_df], ignore_index=True)
                st.success(f"✅ Patrón ejecutado — {len(blocks)} accesos")

    # ── Tabla de últimos accesos ──────────────────────────
    if not st.session_state.log_df.empty:
        st.markdown("---")
        st.markdown("### 📋 Últimos accesos")
        display_df = st.session_state.log_df.tail(30).copy()

        def style_result(val):
            if val == "Hit":
                return "background-color:#0d2e1e; color:#40d98e; font-weight:bold"
            elif val == "Miss":
                return "background-color:#2e0d0d; color:#f87171; font-weight:bold"
            return ""

        def style_miss_type(val):
            if val == "Compulsorio":
                return "color:#f59e0b"
            elif val == "Conflicto/Cap":
                return "color:#fb7185"
            return "color:#556688"

        styled = (display_df.style
                  .map(style_result, subset=["Resultado"])
                  .map(style_miss_type, subset=["Tipo Miss"])
                  .set_properties(**{
                      "background-color": "#12192a",
                      "color": "#c8d8f0",
                      "border-color": "#1e2a40",
                      "font-size": "13px",
                  })
                  .hide(axis="index"))
        st.dataframe(styled, use_container_width=True, height=350)

# ══════════════════════════════════════════════════════════════
#  TAB 2 — ESTADÍSTICAS
# ══════════════════════════════════════════════════════════════
with tab2:
    stats = st.session_state.sim.get_stats()

    if stats["total"] == 0:
        st.info("Aún no hay accesos. Ve a la pestaña **Simular Accesos** para empezar.")
    else:
        # Métricas principales
        c1, c2, c3, c4 = st.columns(4)
        with c1: metric_card("Accesos Totales",  str(stats["total"]),   "")
        with c2: metric_card("Hits",              str(stats["hits"]),   "✅ aciertos")
        with c3: metric_card("Misses",            str(stats["misses"]), "❌ fallos")
        with c4: metric_card("AMAT",              f'{stats["amat"]:.2f}', "ciclos")

        st.markdown("---")

        # Gauges
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.plotly_chart(
                gauge_chart(stats["hit_rate"],  "Hit Rate",  "#40d98e"),
                use_container_width=True)
        with col_g2:
            st.plotly_chart(
                gauge_chart(stats["miss_rate"], "Miss Rate", "#f87171"),
                use_container_width=True)

        st.markdown("---")

        # Gráfico de historia + pastel de misses
        col_h, col_p = st.columns([2, 1], gap="large")
        with col_h:
            st.markdown("##### Evolución acumulada de hits / misses")
            if st.session_state.sim.access_log:
                st.plotly_chart(
                    history_chart(st.session_state.sim.access_log),
                    use_container_width=True)
        with col_p:
            st.markdown("##### Clasificación 3C de misses")
            pie = miss_pie(stats["compulsory"], stats["conflict"])
            if pie:
                st.plotly_chart(pie, use_container_width=True)
            metric_card("Compulsorios",  str(stats["compulsory"]), "primer acceso")
            metric_card("Conflicto/Cap", str(stats["conflict"]),   "reemplazo")

        # Info de configuración
        st.markdown("---")
        st.markdown("##### Configuración activa")
        info_cols = st.columns(4)
        cfg = [
            ("Cache Size", f"{sim.cache_size} B"),
            ("Block Size", f"{sim.block_size} B"),
            ("Sets",       str(stats["num_sets"])),
            ("Política",   sim.policy),
        ]
        for col, (lbl, val) in zip(info_cols, cfg):
            with col: metric_card(lbl, val)

        bits_cols = st.columns(3)
        bcfg = [
            ("TAG bits",    str(stats["tag_bits"])),
            ("INDEX bits",  str(stats["index_bits"])),
            ("OFFSET bits", str(stats["offset_bits"])),
        ]
        for col, (lbl, val) in zip(bits_cols, bcfg):
            with col: metric_card(lbl, val)

# ══════════════════════════════════════════════════════════════
#  TAB 3 — ESTADO VISUAL DE LA CACHÉ
# ══════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### 🗂️ Estado actual de la caché")

    max_vis = min(sim.num_sets, 16)
    if sim.num_sets > 16:
        st.caption(f"Mostrando los primeros 16 de {sim.num_sets} sets.")

    if max_vis <= 8:
        render_cache_state(sim, max_vis)
    else:
        # Tabla condensada para muchos sets
        rows = []
        for s_idx in range(sim.num_sets):
            for w_idx, line in enumerate(sim.sets[s_idx]):
                rows.append({
                    "Set":   s_idx,
                    "Way":   w_idx,
                    "Válido": "✅" if line.valid else "❌",
                    "TAG":   line.tag if line.valid else "—",
                    "Último uso": line.last_used if line.valid else "—",
                    "Frecuencia": line.frequency if line.valid else "—",
                })
        cache_df = pd.DataFrame(rows)
        st.dataframe(cache_df, use_container_width=True, height=500)

    st.markdown("---")
    st.markdown(f"""
    **Leyenda:**
    - 🔵 Línea válida con datos en caché
    - ⬛ Línea vacía (inválida)
    - **TAG**: etiqueta de la dirección almacenada
    - **LU**: timestamp del último uso (para LRU)
    - **F**: frecuencia de uso (para LFU)

    **Configuración:** `{sim.cache_size}B` caché · `{sim.block_size}B` bloque ·
    `{sim.num_sets}` sets · `{sim.associativity}`-way · Política: `{sim.policy}`
    """)

# ══════════════════════════════════════════════════════════════
#  TAB 4 — HISTORIAL COMPLETO
# ══════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### 📖 Historial completo de accesos")

    if st.session_state.log_df.empty:
        st.info("Aún no hay accesos registrados.")
    else:
        df = st.session_state.log_df.copy()

        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filter_result = st.multiselect(
                "Filtrar por resultado", ["Hit", "Miss"], default=["Hit", "Miss"])
        with col_f2:
            filter_miss = st.multiselect(
                "Filtrar tipo de miss",
                ["Compulsorio", "Conflicto/Cap", ""],
                default=["Compulsorio", "Conflicto/Cap", ""])
        with col_f3:
            if not df.empty and "Set" in df.columns:
                sets_available = sorted(df["Set"].unique().tolist())
                filter_sets = st.multiselect("Filtrar por Set", sets_available,
                                             default=sets_available)
            else:
                filter_sets = []

        if filter_result:
            df = df[df["Resultado"].isin(filter_result)]
        if filter_miss:
            df = df[df["Tipo Miss"].isin(filter_miss)]
        if filter_sets:
            df = df[df["Set"].isin(filter_sets)]

        st.caption(f"Mostrando {len(df)} de {len(st.session_state.log_df)} accesos")
        st.dataframe(df, use_container_width=True, height=500)

        # Exportar CSV
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar CSV",
            data=csv,
            file_name="cache_simulation.csv",
            mime="text/csv",
            type="secondary",
        )
