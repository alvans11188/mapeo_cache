# Simulador de Caché CPU

Simulador interactivo de memoria caché desarrollado con **Python + Streamlit**.

## Características

- **Mapeo Directo**, **N-way Asociativo** y **Totalmente Asociativo**
- Políticas de reemplazo: **LRU**, **LFU**, **FIFO**, **Random**
- Desglose de dirección en **TAG / INDEX / OFFSET** (binario)
- Clasificación de misses **3C**: Compulsorios, Conflicto/Capacidad
- Cálculo de **AMAT** (Average Memory Access Time)
- Patrones de acceso predefinidos: Secuencial, Localidad temporal, Stride, Thrashing
- Visualización del estado interno de la caché (sets y ways)
- Historial exportable a CSV
- Gráficos interactivos con Plotly

## Ejecución local

```bash
# Clonar el repositorio
git clone https://github.com/TU_USUARIO/cache-simulator.git
cd cache-simulator

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar
streamlit run app.py
```

##  Estructura del proyecto

```
cache-simulator/
├── app.py              # Aplicación principal
├── requirements.txt    # Dependencias Python
├── README.md           # Este archivo
└── .streamlit/
    └── config.toml     # Configuración del tema
```

##  Deploy en Streamlit Cloud

1. Sube el repositorio a GitHub
2. Ve a [share.streamlit.io](https://share.streamlit.io)
3. Conecta tu cuenta de GitHub
4. Selecciona el repositorio y el archivo `app.py`
5. Haz clic en **Deploy**

##  Parámetros de configuración

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| Tamaño de caché | Total en bytes (potencia de 2) | 256 B |
| Tamaño de bloque | Bytes por bloque (potencia de 2) | 32 B |
| Asociatividad | Vías por set | 1, 2, 4 |
| Política | Algoritmo de reemplazo | LRU |

## 🧮 Fórmulas implementadas

```
num_sets   = cache_size / (block_size × associativity)
offset_bits = log₂(block_size)
index_bits  = log₂(num_sets)
tag_bits    = 32 - index_bits - offset_bits
AMAT        = 1 + (miss_rate × 100)  ciclos
```

---
Desarrollado para el curso de Arquitectura de Computadores
