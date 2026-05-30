# Lead-Lag Analysis — Findings

**TL;DR — No hay lead-lag predictivo explotable entre exchanges spot.** Los
precios se mueven de forma esencialmente simultánea (sub-100ms). El único patrón
direccional encontrado (Binance "siguiendo" a todos por 200ms) es un **artefacto
de latencia de recepción**, no una señal negociable. Conclusión estratégica: el
mercado spot de BTC es eficiente; el edge real está en **funding / derivados**.

> Esto documenta una hipótesis que **exploramos con método y descartamos**. El
> análisis vive en `scripts/leadlag_analysis.py` (es análisis exploratorio, no
> código de producción).

---

## Pregunta

¿Algún exchange "lidera" (incorpora información primero) y otro "sigue", de modo
que el movimiento del líder prediga el del seguidor en los próximos ms/segundos?
Eso sería arbitraje **predictivo** (lead-lag), distinto del espacial.

## Método

Cross-correlation con lag (estándar en la literatura):

1. Mid-price `= (bid + ask) / 2` por exchange desde `data/recordings/market_data.jsonl`
   (454k ticks reales, ~67 min, 6 exchanges).
2. Resampleo a grilla regular (100ms; validado también a 50ms y 250ms), forward-fill.
3. Log-returns por serie.
4. Para cada par, correlación de Pearson de `A[t]` vs `B[t − lag]`, barriendo
   lags de −5s a +5s.
5. El lag que maximiza |correlación| indica quién lidera y por cuánto tiempo.

Kraken se excluyó: 2.3% de cobertura (1143 ticks) — demasiado disperso para ser
fiable. Cobertura del resto: bitstamp 69%, gemini 63%, binance 47%, coinbase 30%,
okx 27%.

---

## Hallazgo 1 — Entre coinbase / okx / bitstamp / gemini: movimientos simultáneos

Las curvas de correlación tienen un pico nítido **exactamente en lag 0** y caen a
la mitad en ±100ms. Ejemplos:

```
coinbase vs okx:    pico @ 0ms = 0.380   (0.12 en ±100ms)
bitstamp vs gemini: pico @ 0ms = 0.213
```

No hay líder: cuando uno se mueve, el otro ya se movió dentro del mismo bin de
100ms. **Cero capacidad predictiva** — no se puede anticipar nada porque la
información llega a la vez.

## Hallazgo 2 — Binance va ~200ms *por detrás* de todos (único patrón direccional)

```
binance vs okx:      pico @ −200ms = 0.428   (okx "lidera" a binance)
binance vs bitstamp: lidera bitstamp por 200ms
binance vs coinbase: lidera coinbase por 200ms
binance vs gemini:   lidera gemini  por 200ms
```

A primera vista, okx→binance (corr 0.43, lead 200ms ≫ 5ms de latencia de
ejecución) parecería explotable. **No lo es.**

### Tres pruebas de que el offset de 200ms es artefacto de latencia, no alpha

1. **Es idéntico (200ms exactos) en los 4 pares independientes.** Un lead-lag
   genuino entre cuatro venues distintos jamás daría el mismo offset constante.
   Una latencia diferencial *por venue* sí produce exactamente eso.

2. **Robusto a la resolución pero pegado a 200ms.** A 50ms el pico sigue en 200ms
   (no baja a 50/100/150); a 250ms se redondea a un solo bin. Es un offset fijo
   del reloj de recepción, no un proceso de difusión de precio (que se
   reescalaría con la resolución).

3. **El signo contradice la realidad del mercado.** Binance es el venue de mayor
   liquidez de BTC del mundo; en el mercado *lidera* el price discovery. Que en
   nuestros datos *siga* a todos por 200ms solo puede significar que sus mensajes
   **llegan a nuestro cliente 200ms tarde** (routing/distancia al endpoint, o
   batching del stream). El libro de Binance no está ejecutable al precio viejo
   durante 200ms — simplemente lo recibimos tarde. No hay nada que arbitrar.

### Por qué importa el sesgo de timestamp

Los timestamps son `ws_received_at` (hora de recepción de *nuestro* cliente), que
mezcla el lead real de mercado con la latencia diferencial de feed por venue. Sin
timestamps de origen del exchange no se pueden separar las dos componentes — y es
precisamente por eso que el "lag" de Binance es sospechoso y no negociable.

---

## Conclusión

- **Lead-lag predictivo explotable: no existe en estos datos.** El método
  encontró lo esperable de venues de BTC modernos: el precio se mueve de forma
  casi simultánea (sub-100ms) entre exchanges. **El mercado spot es eficiente.**
- El único candidato que cruzó los umbrales es un **falso positivo por latencia
  de recepción**, no una señal real.
- Esto **refuerza** la decisión de diseño: el edge está en el **arbitraje
  espacial** (diferencias de precio simultáneas entre libros) y, sobre todo, en
  **funding / derivados** — donde existe una dislocación estructural y persistente
  que el mercado spot eficiente no ofrece.

## Caveats metodológicos

- ffill en bins tranquilos inyecta returns cero; por eso reportamos el *lift*
  sobre lag-0 para controlar correlación contemporánea inflada.
- Un lead a la resolución de la grilla (un bin de 100ms) está en el límite de lo
  medible y probablemente refleja jitter de timestamp, no alpha.
- Análisis exploratorio sobre una ventana de ~67 min; no es una garantía
  intertemporal, pero el resultado (eficiencia spot) es consistente con la
  literatura de microestructura de cripto.

---

*Reproducir:* `python scripts/leadlag_analysis.py`
(opciones: `--resample-ms`, `--max-lag-s`, `--min-coverage`)
