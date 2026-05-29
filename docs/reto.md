El Desafío: Arbitraje de Bitcoin
El Problema
Bitcoin es el activo financiero más negociado del mundo digital. Se transa simultáneamente en cientos de exchanges alrededor del mundo, las 24 horas del día, los 7 días de la semana, sin interrupciones ni cierres de mercado.

Dado que cada exchange opera de forma independiente, con su propia liquidez, su propia base de usuarios y su propio libro de órdenes (order book), los precios nunca son exactamente iguales entre plataformas. Las fuerzas de oferta y demanda actúan de forma distinta en cada mercado, generando constantemente divergencias de precio que pueden durar milisegundos o varios segundos.

Estas divergencias son la materia prima del arbitraje: la práctica de explotar diferencias de precio del mismo activo en mercados distintos para obtener una ganancia con riesgo teórico cercano a cero. En los mercados financieros tradicionales, los grandes fondos de inversión y los traders de alta frecuencia (HFT — High Frequency Trading) dedican infraestructura millonaria para capturar estas oportunidades en fracciones de segundo.

En el mundo cripto, estas oportunidades son más frecuentes y accesibles, porque los mercados son más fragmentados, menos eficientes, y las APIs de los exchanges están disponibles de forma pública y gratuita. El campo de juego está abierto para cualquier desarrollador que tenga la velocidad y la inteligencia para aprovecharlo.

Tu misión es construir ese sistema.

El Challenge
Deberás diseñar, desarrollar y desplegar un sistema de trading automático que sea capaz de detectar oportunidades de arbitraje en tiempo real y simular su ejecución de forma inteligente. El sistema debe cumplir con los siguientes requisitos funcionales:

Monitoreo en tiempo real de order books de BTC en dos o más exchanges. El sistema debe conectarse mediante WebSockets o polling a los feeds públicos de datos de mercado y mantener una visión actualizada del mejor precio de compra (Ask) y venta (Bid) en cada plataforma.
Detección de oportunidades de arbitraje. Cuando el precio Ask de un exchange sea inferior al precio Bid de otro, existe una oportunidad de arbitraje. El sistema debe identificarla en el momento en que ocurre, calcular su rentabilidad neta y decidir si ejecutarla.
Ejecución simulada de la operación. Al detectar una oportunidad rentable, el sistema debe registrar y simular la compra en el exchange de precio menor y la venta simultánea en el exchange de precio mayor, respetando las restricciones de liquidez del order book.
Consideración de costos reales de operación. Toda oportunidad debe evaluarse neta de comisiones (trading fees), costos de retiro (withdrawal fees), slippage estimado y latencia de red. Una oportunidad que parezca rentable en bruto puede resultar negativa al considerar estos factores.
Gestión de órdenes parciales y balance de wallets. El sistema debe manejar escenarios donde la liquidez disponible en el order book no cubra el volumen completo de la operación, ejecutando órdenes parciales cuando sea necesario. Los balances de cada wallet deben actualizarse correctamente tras cada operación simulada.
Registro y visualización del rendimiento. El sistema debe llevar un historial de todas las oportunidades detectadas, operaciones ejecutadas, ganancias y pérdidas acumuladas, y presentar esta información de forma clara en la interfaz web.
Ejemplo
Considera el siguiente escenario en tiempo real. El sistema detecta la siguiente divergencia en el mercado de BTC/USDT:

Exchange	Acción	Precio BTC	Fee estimado (0.1%)	Precio neto
Exchange A (ej. Kraken)	Comprar (Ask)	$70,000.00	$70.00	$70,070.00
Exchange B (ej. Binance)	Vender (Bid)	$70,250.00	$70.25	$70,179.75
Tu bot evalúa la operación y ejecuta:

Compra 1 BTC en Exchange A a $70,000 + fee $70.00 = costo total $70,070.00
Vende 1 BTC en Exchange B a $70,250 − fee $70.25 = ingreso neto $70,179.75
Ganancia neta por operación: $109.75 USD por BTC negociado

Un sistema bien construido puede detectar decenas de estas oportunidades por hora. La diferencia entre un bot promedio y uno excepcional no está solo en detectarlas, sino en priorizarlas, ejecutarlas con la latencia más baja posible y gestionar el riesgo cuando el mercado se mueve en contra durante la ejecución.

Datos de Mercado: Exchanges y APIs Disponibles
Puedes conectarte a cualquier exchange que ofrezca API pública de datos de mercado. A continuación encontrarás los principales exchanges recomendados, junto con sus documentaciones oficiales:

Binance — El exchange de mayor volumen del mundo. API REST · WebSocket Streams
Kraken — Uno de los exchanges más antiguos y confiables. API REST · WebSocket API
Coinbase Advanced Trade — Exchange regulado del mercado estadounidense. API REST · WebSocket Feed
OKX — Alto volumen, especialmente en mercados asiáticos. API REST · WebSocket API
Bybit — Exchange en fuerte crecimiento global. API REST · WebSocket API
Bitfinex — Plataforma con alta liquidez institucional. API REST · WebSocket API
KuCoin — Amplia variedad de pares y mercados alternativos. API REST · WebSocket API
Gate.io — Uno de los exchanges con mayor número de activos listados. API REST y WebSocket
Bitstamp — Exchange europeo con larga trayectoria. API REST · WebSocket API
Gemini — Exchange regulado con datos institucionales. API REST · WebSocket API
Para explorar el universo completo de exchanges y comparar volúmenes, spreads y liquidez en tiempo real, puedes consultar los siguientes agregadores de mercado:

CoinMarketCap — Mercados de Bitcoin · Comparativa de precios y volúmenes por exchange en tiempo real.
CoinGecko — Mercados de Bitcoin · Datos alternativos de liquidez, spread y confiabilidad por exchange.
TradingView — BTC/USD · Visualización de precios multi-exchange en tiempo real.
Qué Estamos Buscando
Tu solución será evaluada por un jurado técnico especializado en sistemas financieros y desarrollo de software. Los criterios de evaluación son los siguientes:

Velocidad y eficiencia en la detección de oportunidades. ¿Con qué latencia tu sistema identifica una divergencia de precio desde que ocurre en el mercado? ¿Usas WebSockets o polling? ¿Cómo optimizas el procesamiento de datos en tiempo real?
Precisión en el cálculo de rentabilidad neta. ¿Tu sistema considera correctamente los fees de cada exchange, el slippage estimado y los riesgos de ejecución antes de tomar una decisión? ¿Evita ejecutar operaciones que parezcan rentables en bruto pero resulten negativas en neto?
Solidez y robustez de la lógica de negocio. ¿Cómo maneja el sistema situaciones de baja liquidez, órdenes parciales o movimientos bruscos de mercado durante la ejecución? ¿Existe algún mecanismo de gestión de riesgo o de circuit breaker ante condiciones adversas?
Estrategia e inteligencia del bot. ¿El sistema simplemente detecta la primera oportunidad disponible o es capaz de priorizarlas, comparar múltiples pares simultáneamente o implementar alguna estrategia más sofisticada (por ejemplo, arbitraje triangular, arbitraje estadístico, etc.)?
Calidad de la arquitectura y el código. ¿El sistema está bien estructurado, es mantenible y escalable? ¿El código es legible, está documentado y sigue buenas prácticas de ingeniería de software?
Experiencia y presentación en la interfaz web. La solución debe estar desplegada como web app funcional y accesible desde un navegador. Se valorará positivamente una interfaz que permita visualizar en tiempo real el estado del mercado, las oportunidades detectadas, las operaciones ejecutadas y el P&L acumulado.
Entrega y Despliegue
Tu solución debe estar desplegada y accesible públicamente como aplicación web antes del cierre del periodo de entrega. Asegúrate de que el sistema esté corriendo y sea funcional en el momento de la evaluación.

Plataformas sugeridas para el despliegue (gratuitas o con tier gratuito suficiente):

Vercel — Ideal para frontends y APIs en Next.js, React, etc.
Railway — Backends, bots y servicios con soporte para cualquier lenguaje.
Render — Web services, workers y bases de datos en la nube.
Fly.io — Despliegue de aplicaciones con baja latencia global.
Google Cloud Run — Contenedores serverless con generoso free tier.
AWS Free Tier — EC2, Lambda y servicios managed para arquitecturas más complejas.
Junto con la URL de tu aplicación, deberás proporcionar acceso al repositorio de código (público o con acceso compartido) para que el jurado pueda revisar la implementación. Un README claro con la descripción de la arquitectura, instrucciones de uso y decisiones técnicas relevantes será valorado positivamente.

El Objetivo
Construir el bot de arbitraje de Bitcoin más rápido, inteligente y robusto posible. No existe una única solución correcta: hay decenas de estrategias válidas, arquitecturas posibles y niveles de sofisticación alcanzables en 48 horas. Lo que buscamos no es la solución perfecta, sino la que demuestre el mayor dominio técnico, la mejor capacidad de razonamiento bajo presión y la ejecución más sólida dentro del tiempo disponible.

Los mercados financieros son brutalmente eficientes: las ineficiencias que existen hoy pueden desaparecer mañana. Los mejores sistemas de arbitraje del mundo operan con latencias de microsegundos y procesan millones de eventos por segundo. En este challenge no llegamos a eso, pero el principio es el mismo: velocidad, precisión y determinación.

Las ineficiencias del mercado están ahí afuera. Tu trabajo es capturarlas antes que nadie.

---

## Criterios de excelencia — Cómo los atacamos

El reto distingue explícitamente entre un bot promedio y uno excepcional. Los tres ejes de diferenciación y cómo los cubrimos:

---

### 1. Priorización de oportunidades

**Qué significa**: no ejecutar la primera oportunidad detectada, sino rankear todas las activas y elegir la de mayor valor esperado neto.

**Componente**: `OpportunityScorer` — capa entre el scanner y el ejecutor. Mantiene una priority queue de oportunidades vigentes y les asigna un score compuesto:

```
score = net_spread_pct
      × min(ask_depth_A, bid_depth_B)    # liquidez disponible
      × freshness_decay(age_ms)          # penaliza spreads viejos
      − execution_risk_penalty           # ajuste por volatilidad reciente
```

El bot ejecuta la de mayor score, no la primera detectada. Si dos exchanges tienen spread similar pero uno tiene 10× la liquidez, el sistema lo sabe y lo prefiere.

**Fase**: 3 (h8–h20), una vez que el scanner básico ya corre. El scanner de MVP lista oportunidades; el scorer las ordena.

---

### 2. Latencia mínima (medida y optimizada)

**Qué significa**: medir cuánto tarda el sistema desde que llega el tick de precio hasta que se toma la decisión de ejecutar. Ese número debe ser visible en el dashboard y debe ser bajo.

**Componente**: instrumentación de latency pipeline en todos los adapters y en el ejecutor.

Cada evento lleva timestamps encadenados:

```
ws_received_at    → normalizer_out_at  → scanner_evaluated_at
→ scorer_ranked_at → executor_decided_at
```

La latencia de decisión = `executor_decided_at − ws_received_at`. Se persiste en DuckDB y se expone en el dashboard como `p50 / p95 / p99` de latencia.

**Optimizaciones concretas**:
- Un solo `asyncio` event loop, sin threading para el hot path
- BBO state en dict en memoria (no DuckDB en el hot path — DuckDB solo para persists async)
- WS adapters en tasks independientes, no bloqueantes entre sí
- Stale quote threshold: si el BBO tiene >500ms, se marca como stale y no se ejecuta

**Fase**: 2 (h4–h8) — los timestamps van desde el principio, no se agregan después. El dashboard de latencia es Fase 4.

---

### 3. Gestión de riesgo durante la ejecución

**Qué significa**: entre que detectas la oportunidad y "ejecutas" (simulado), el mercado puede haberse movido. Un bot ingenuo ejecuta de todas formas y registra una pérdida.

**Componente**: `ExecutionSimulator` con tres mecanismos de protección:

**a) Validación pre-ejecución (precio stale)**
Antes de ejecutar, re-verifica que el spread sigue siendo positivo neto con los precios actuales. Si el spread colapsó, aborta y registra como `ABORTED_STALE`.

**b) Circuit breaker por volatilidad**
Si en los últimos 10 segundos el precio de BTC se movió más de un umbral configurable (ej. 0.05%), suspende ejecuciones por N segundos. La lógica: en alta volatilidad, los spreads son noise, no arbitraje real.

**c) Partial fill con exit condition**
Si la liquidez disponible cubre solo el 30% del q* óptimo, el sistema puede elegir no ejecutar (el costo fijo de withdrawal fee no se amortiza). Umbral configurable: `min_fill_ratio`.

Los tres eventos (ABORTED_STALE, CIRCUIT_BREAKER_OPEN, SKIPPED_MIN_FILL) se registran en DuckDB y se muestran en el dashboard — el jurado puede ver que el sistema sabe cuándo no operar.

**Fase**: 3 (h8–h20) junto con el executor completo. El circuit breaker es ~30 líneas de Python pero es el feature de gestión de riesgo más visible en demo.

---

### Resumen de componentes por fase

| Fase    | Componente nuevo                     | Criterio cubierto        |
|---------|--------------------------------------|--------------------------|
| h0–h4   | WSAdapter + Normalizer + Scanner     | base para los tres       |
| h4–h8   | Timestamp pipeline, DuckDB persist   | Latencia (medición)      |
| h8–h20  | OpportunityScorer, OptimalSizer      | Priorización + Sizing    |
| h8–h20  | ExecutionSimulator completo          | Gestión de riesgo        |
| h20–h36 | Dashboard: latency p95, circuit state| Latencia (visualización) |
