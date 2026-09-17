```python
import weasyprint
from weasyprint import HTML

html_content = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>ТЗ: ИИ-Агент и Автономная Система Продаж (Telegram + Web3 Admin)</title>
    <style>
        @page {
            size: A4;
            margin: 15mm 12mm;
            background-color: #0b0e14;
        }
        *, *::before, *::after {
            box-sizing: border-box;
        }
        body {
            font-family: 'Helvetica Neue', Arial, sans-serif;
            color: #c5cdd9;
            background-color: #0b0e14;
            font-size: 9.5pt;
            line-height: 1.5;
            margin: 0;
            padding: 0;
        }
        
        .header-banner {
            background: linear-gradient(135deg, #131b2e 0%, #1a0b2e 100%);
            border: 1px solid #2d3748;
            border-left: 5px solid #00f2fe;
            border-radius: 8px;
            padding: 20px 24px;
            margin-bottom: 20px;
        }
        .header-title {
            color: #ffffff;
            font-size: 20pt;
            font-weight: 800;
            margin: 0 0 6px 0;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .header-subtitle {
            color: #00f2fe;
            font-size: 11pt;
            font-weight: 600;
            margin: 0;
        }
        .header-meta {
            margin-top: 12px;
            font-size: 8.5pt;
            color: #a0aec0;
            display: table;
            width: 100%;
        }
        .meta-cell {
            display: table-cell;
            padding-right: 15px;
        }

        h2 {
            color: #ffffff;
            font-size: 13pt;
            font-weight: 700;
            border-bottom: 2px solid #2d3748;
            padding-bottom: 6px;
            margin-top: 22px;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        h2::before {
            content: "❖ ";
            color: #00f2fe;
        }
        
        h3 {
            color: #4facfe;
            font-size: 10.5pt;
            font-weight: 600;
            margin-top: 14px;
            margin-bottom: 6px;
        }

        p, ul, ol {
            margin-top: 0;
            margin-bottom: 10px;
        }
        
        ul, ol {
            padding-left: 18px;
        }

        li {
            margin-bottom: 4px;
        }

        .card {
            background: #131722;
            border: 1px solid #2a2e3d;
            border-radius: 6px;
            padding: 12px 16px;
            margin-bottom: 14px;
        }

        .card-accent {
            border-left: 3px solid #7f53ac;
        }

        .badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 7.5pt;
            font-weight: bold;
            text-transform: uppercase;
        }
        .badge-cyan { background: rgba(0, 242, 254, 0.15); color: #00f2fe; border: 1px solid #00f2fe; }
        .badge-purple { background: rgba(127, 83, 172, 0.2); color: #c86dd7; border: 1px solid #c86dd7; }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
            margin-bottom: 14px;
            font-size: 9pt;
        }

        th {
            background-color: #1a202c;
            color: #00f2fe;
            text-align: left;
            padding: 8px 10px;
            border: 1px solid #2d3748;
            font-weight: 600;
        }

        td {
            padding: 7px 10px;
            border: 1px solid #2d3748;
            background-color: #131722;
        }

        tr:nth-child(even) td {
            background-color: #171c28;
        }

        .tech-stack-grid {
            display: table;
            width: 100%;
            table-layout: fixed;
            margin-bottom: 14px;
        }
        .tech-col {
            display: table-cell;
            width: 33.3%;
            padding: 4px;
        }

        .analysis-box {
            background: rgba(255, 171, 0, 0.05);
            border: 1px solid rgba(255, 171, 0, 0.3);
            border-radius: 6px;
            padding: 10px 14px;
            margin-top: 10px;
            margin-bottom: 14px;
        }
        .analysis-box h4 {
            color: #ffab00;
            margin: 0 0 6px 0;
            font-size: 9.5pt;
            text-transform: uppercase;
        }
        
        .code-inline {
            font-family: monospace;
            background: #1a202c;
            color: #00f2fe;
            padding: 2px 4px;
            border-radius: 3px;
            font-size: 8.5pt;
        }

        h2, h3 {
            page-break-after: avoid;
        }
        .card, table, .analysis-box {
            page-break-inside: avoid;
        }
    </style>
</head>
<body>

    <div class="header-banner">
        <div class="header-title">ТЕХНИЧЕСКОЕ ЗАДАНИЕ</div>
        <div class="header-subtitle">Автономный ИИ-Агент Продаж (Telegram Business) & Web3 Админ-Панель</div>
        <div class="header-meta">
            <div class="meta-cell"><strong>Модель ИИ:</strong> Google Gemini 1.5 Flash / 2.0 Flash</div>
            <div class="meta-cell"><strong>Архитектура:</strong> Multi-Agent Proactive Pipeline</div>
            <div class="meta-cell"><strong>Дата:</strong> Август 2026</div>
        </div>
    </div>

    <div class="analysis-box">
        <h4>Разбор прикрепленных скриншотов (Анализ "ИИ-Штаба из Instagram")</h4>
        <p style="margin-bottom:0;">
            На представленных скриншотах изображена <strong>визуализация нейросетевой архитектуры / графа активации слоев (ResBlock x3, ResBlock x6, Dense, ReLU skip connection)</strong> в реальном времени (например, инструмент TensorBoard, Netron или кастомный WebGL-визуализатор обучения/инференса нейросети). 
            <br>
            <strong>Вердикт:</strong> Это <u>не интерфейс управления готовым ИИ-агентом</u> и не "штаб сотрудников". В Instagram подобные видео используются маркетингово для визуального эффекта ("Sci-Fi эстетика"). Однако в рамках данного ТЗ мы спроектируем <strong>Web3 Cyber-Admin Panel</strong>, которая воссоздаст аналогичную премиальную футуристичную визуализацию графа автономных задач и активности мультиагентной системы.
        </p>
    </div>

    <h2>1. Общее описание системы</h2>
    <p>
        Целью проекта является разработка автономного мультиагентного ИИ-комплекса, работающего через <strong>Telegram Business API / UserBot (Telethon/Pyrogram)</strong>. ИИ-агент функционирует без прямого участия человека, выстраивает полноценный цикл продаж, автоматически квалифицирует лидов, делает проактивные фоллоу-апы (follow-up), принимает оплату в <strong>USDT TRC-20</strong> и инициирует безопасные сделки у крипто-гарантов (Escrow API).
    </p>

    <h2>2. Архитектура ИИ-Агента (Multi-Agent Subsystems)</h2>
    <p>Вместо одного промпта система делится на ролевые модули под управлением <strong>Gemini 1.5/2.0 Flash</strong> (оптимальный баланс скорости, окна контекста в 1M+ токенов и стоимости):</p>
    
    <div class="card card-accent">
        <h3>A. Главный Оркестратор (Orchestrator Agent / Planner)</h3>
        <ul>
            <li>Автономно анализирует состояние диалога и текущую стадию воронки.</li>
            <li>Определяет целевое действие без явной команды пользователя (автономность).</li>
            <li>Формирует задачи для узкоспециализированных суб-агентов.</li>
        </ul>
    </div>

    <div class="card">
        <h3>B. Менеджер по продажам и консультациям (Sales & Knowledge Agent)</h3>
        <ul>
            <li>Работает с векторной базой знаний (RAG на Qdrant / Pgvector).</li>
            <li>Отвечает на вопросы о товарах/услугах, стоимости, сроках и условиях.</li>
            <li>Эмулирует манеру речи топового human-менеджера (без «роботизированных» шаблонов, с паузами на "печать").</li>
        </ul>
    </div>

    <div class="card card-accent">
        <h3>C. Проактивный Фоллоу-ап Агент (Follow-Up & CRM Agent)</h3>
        <ul>
            <li>Мониторит "зависшие" диалоги в фоновом режиме (CRON / Celery).</li>
            <li>Автономно принимает решение: когда подтолкнуть клиента к сделке, какую скидку или аргумент предложить, учитывая контекст прошлых сообщений.</li>
            <li>Не спамит: рассчитывает оптимальный тайминг (через 2 часа, 24 часа, 3 дня).</li>
        </ul>
    </div>

    <div class="card">
        <h3>D. Финансовый & Escrow Агент (Payment & Escrow Agent)</h3>
        <ul>
            <li>Генерирует уникальные USDT TRC-20 адреса под каждую сделку.</li>
            <li>Мониторит блокчейн Tron через TronGrid / RPC node на приход средств.</li>
            <li>Взаимодействует с API гарант-сервисов (или автоматизирует создание Escrow-сделок).</li>
        </ul>
    </div>

    <h2>3. Технический стек проекта</h2>
    <div class="tech-stack-grid">
        <div class="tech-col">
            <div class="card">
                <span class="badge badge-cyan">Backend & Core</span>
                <ul style="margin-top:6px; font-size:8.5pt;">
                    <li>Python 3.11+ / FastAPI</li>
                    <li>Pyrogram / Telethon</li>
                    <li>Celery + Redis (Задачи)</li>
                    <li>PostgreSQL (Основная БД)</li>
                </ul>
            </div>
        </div>
        <div class="tech-col">
            <div class="card">
                <span class="badge badge-purple">AI & RAG</span>
                <ul style="margin-top:6px; font-size:8.5pt;">
                    <li>Google Gemini 1.5/2.0 Flash</li>
                    <li>Qdrant / Pgvector (Vector DB)</li>
                    <li>LangChain / LangGraph</li>
                    <li>LlamaIndex (Документы)</li>
                </ul>
            </div>
        </div>
        <div class="tech-col">
            <div class="card">
                <span class="badge badge-cyan">Frontend Web3</span>
                <ul style="margin-top:6px; font-size:8.5pt;">
                    <li>Next.js 14 / React</li>
                    <li>Tailwind CSS + Shadcn UI</li>
                    <li>Three.js / React Flow (Графы)</li>
                    <li>Wagmi / Ethers.js (Web3)</li>
                </ul>
            </div>
        </div>
    </div>

    <h2>4. Функционал Web3 Админ-Панели (Cyberpunk / Web3 Style)</h2>
    <p>Административная панель выполняется в стиле темно-неонового киберпанкового интерфейса (темный фон, неоновые связи, аналитические графы, схожие со скриншотами пользователя):</p>
    
    <table>
        <thead>
            <tr>
                <th>Модуль</th>
                <th>Функциональные возможности</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>1. Live Organism (Граф Агентов)</strong></td>
                <td>Интерактивный 3D/2D граф (Three.js/React Flow), показывающий связи между агентами, входящими сообщениями и активными задачами в реальном времени.</td>
            </tr>
            <tr>
                <td><strong>2. Live Dialogs & Takeover</strong></td>
                <td>Просмотр всех диалогов в реальном времени. Функция "Manual Override" (перехват управления человеком в 1 клик).</td>
            </tr>
            <tr>
                <td><strong>3. Knowledge Base (RAG)</strong></td>
                <td>Загрузка PDF, DOCX, TXT с прайсами и регламентами. Автоматическая индексация в векторную базу для Gemini.</td>
            </tr>
            <tr>
                <td><strong>4. Crypto Wallet & Sales</strong></td>
                <td>Мониторинг USDT TRC-20 транзакций, балансы, автоматический вывод средств, история сделок у гарантов.</td>
            </tr>
            <tr>
                <td><strong>5. Prompt & Behavior Tuning</strong></td>
                <td>Редактирование системных промптов, тональности, лимитов фоллоу-апов, автономности агента.</td>
            </tr>
        </tbody>
    </table>

    <h2>5. Сценарий работы: Крипто-Платежи и Гарант (USDT TRC-20)</h2>
    <ol>
        <td><strong>Шаг 1. Формирование заказа:</strong> ИИ-агент доводит клиента до согласия на покупку и высчитывает итоговую сумму.</td>
        <td><strong>Шаг 2. Выбор способа:</strong> Агент предлагает прямую оплату на USDT TRC-20 или через Escrow (Гарант).</td>
        <td><strong>Шаг 3. Прямая оплата:</strong> Backend генерирует HD-адрес кошелька TRC-20. Агент отправляет реквизиты и QR-код. При подтверждении 19+ блоков в TronGrid агент уведомляет клиента и передает заказ в статус "Оплачен".</td>
        <td><strong>Шаг 4. Работа с Гарантом:</strong> Агент подключается к API Escrow-сервиса (или Telegram Escrow Bot), создает сделку, отправляет ссылку клиенту и отслеживает статус внесения депозита.</td>
    </ol>

    <h2>6. Этапы и сроки разработки</h2>
    <table>
        <thead>
            <tr>
                <th>Этап</th>
                <th>Описание работ</th>
                <th>Срок</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Этап 1</strong></td>
                <td>Проектирование архитектуры, настройка Gemini Flash API, база данных, Pyrogram/Telegram Integration.</td>
                <td>10 дней</td>
            </tr>
            <tr>
                <td><strong>Этап 2</strong></td>
                <td>Разработка Multi-Agent движка (LangGraph), фоллоу-ап трекера, интеграция RAG базы знаний.</td>
                <td>14 дней</td>
            </tr>
            <tr>
                <td><strong>Этап 3</strong></td>
                <td>Интеграция USDT TRC-20 (TronGrid API) и модуля сделок у Гарантов.</td>
                <td>8 дней</td>
            </tr>
            <tr>
                <td><strong>Этап 4</strong></td>
                <td>Разработка Web3 Админ-панели (Next.js, Three.js визуализация графов, Live-чат, управления промптами).</td>
                <td>14 дней</td>
            </tr>
            <tr>
                <td><strong>Этап 5</strong></td>
                <td>Тестирование, стресс-тесты, отладка краевых сценариев, запуск.</td>
                <td>6 дней</td>
            </tr>
        </tbody>
    </table>

</body>
</html>
"""

html_path = "tz_ai_agent_telegram.html"
pdf_path = "tz_ai_agent_telegram.pdf"

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

HTML(filename=html_path).write_pdf(pdf_path)
print(f"PDF successfully generated: {pdf_path}")


```

```text
PDF successfully generated: tz_ai_agent_telegram.pdf


```

Your PDF document is ready


---

### Разбор ваших скриншотов («Штаб ИИ-агентов из Instagram»)

На изображениях показана **визуализация графа активации слоев и структуры нейросети** в реальном времени (вызовы блоков `ResBlock x3`, `ResBlock x6`, активации `ReLU`, `Dense`-слои и `Skip-connections`).

* **Что это на самом деле:** Это не стандартный пользовательский интерфейс для диалогов, а 3D UI/WebGL визуализация работы нейросетевых моделей (подобные интерфейсы делают в TensorBoard, Netron, либо кастомных визуализаторах на Three.js/WebGL для демонстрации работы ИИ).
* **Можно ли сделать такой же Web3-дизайн для панели управления?** **Да, абсолютно.** В админ-панели мы используем стек **Next.js + Three.js / React Flow**, чтобы визуализировать мультиагентный «мозг» в виде неоновых узлов и связей между входящими клиентами, Telegram-ботом, менеджерами и модулем крипто-оплаты.

---

# ДЕТАЛЬНОЕ ТЕХНИЧЕСКОЕ ЗАДАНИЕ (ТЗ)

**На разработку автономной мультиагентной системы продаж в Telegram (Business Bot) + Web3 Admin Panel**

---

## 1. Концепция и ключевые требования

Система представляет собой **автономный ИИ-комплекс (Business Bot)**, эмулирующий работу топ-менеджера по продажам.

* **Автономность (Proactive Decision Engine):** ИИ не просто отвечает на команды («/start», «/help»), а самостоятельно ведет клиента по воронке, определяет готовность к покупке, инициирует фоллоу-апы (дожимы), рассчитывает скидки и завершает сделки.
* **Ядро ИИ:** Модель уровня **Google Gemini 1.5 / 2.0 Flash**. Выбор идеален благодаря контекстному окну (1M+ токенов), высокой скорости отклика (<1 сек), низким затратам на API и отличному пониманию русского и английского языков.
* **Финансовый модуль:** Автоматический прием **USDT (TRC-20)** и автоматическое проведение сделок через **крипто-гарантов (Escrow API)**.
* **Интерфейс:** Киберпанк / Web3 Админ-панель с визулом графов активности (как на ваших скриншотах).

---

## 2. Архитектура ИИ-Агента (Multi-Agent Architecture)

Чтобы ИИ не «галлюцинировал» и не допускал ошибок, единый промпт разбивается на ролевую систему суб-агентов под управлением оркестратора **LangGraph / AutoGen**:

```
                         ┌────────────────────────────────┐
                         │   Telegram Business API/User   │
                         └───────────────┬────────────────┘
                                         │ (Входящее сообщение)
                                         ▼
                         ┌────────────────────────────────┐
                         │  Orchestrator Agent (Planner)  │
                         └───────────────┬────────────────┘
                                         │
       ┌─────────────────────────────────┼─────────────────────────────────┐
       ▼                                 ▼                                 ▼
┌──────────────┐                ┌────────────────┐                ┌────────────────┐
│ Sales Agent  │                │ Follow-Up Agent│                │ Payment Agent  │
│ (Консультант)│                │ (Дожим лидов)  │                │ (USDT & Escrow)│
└──────┬───────┘                └───────┬────────┘                └───────┬────────┘
       │                                │                                 │
       └────────────────────────────────┼─────────────────────────────────┘
                                         ▼
                         ┌────────────────────────────────┐
                         │  Knowledge Base (RAG Qdrant)   │
                         └────────────────────────────────┘

```

1. **Orchestrator Agent (Планировщик / Мозг):**
* Анализирует контекст переписки.
* Определяет намерение клиента (консультация, торговля, оплата, жалоба, задержка с ответом).
* Направляет задачу соответствующему модулю.


2. **Sales & Knowledge Agent (Менеджер продаж + RAG):**
* Работает с базой знаний (цены, услуги, FAQ, наличие).
* Эмулирует живого сотрудника: делает паузы перед ответом (имитация печати `typing...`), использует естественную речь, адаптируется под тон клиента.
* Обрабатывает возражения (дорого, не уверен, нужно подумать).


3. **Proactive Follow-Up Agent (Автономный Дожим):**
* Фоновый сервис (Celery/Redis), проверяющий диалоги в режиме 24/7.
* Если клиент прекратил диалог на этапе обсуждения цены или реквизитов, агент автономно оценивает ситуацию и пишит подталкивающее сообщение через задержку (например, 2 часа, 24 часа).
* Оценивает лимиты (не более N напоминаний, чтобы избегать бана/спама).


4. **Crypto Payment & Escrow Agent (Финансовый модуль):**
* Генерирует уникальный USDT TRC-20 адрес под каждую оплату.
* Отслеживает транзакцию в сети Tron (через TronGrid / RPC node).
* Умеет сопоставлять сумма-клиент и менять статус заказа на «Оплачено».
* При запросе безопасной сделки вызывает API Escrow-сервиса, создает сделку и отправляет ссылку/инструкцию клиенту.



---

## 3. Требования к Web3 Админ-Панели (Cyberpunk UI)

Админ-панель должна совмещать функционал CRM и визуальный стиль футуристичного центра управления.

### Разделы интерфейса:

1. **Live Neural Graph («Штаб-Организм»):**
* Визуализация графа задач на Three.js / Canvas в стиле представленных вами скриншотов.
* Неоновые связи, показывающие активные диалоги, работающих суб-агентов, входящий поток сообщений и валидацию транзакций.


2. **Live Dialogs & Manual Override (Живой чат и Перехват):**
* Возможность видеть все диалоги Telegram в реальном времени.
* **Ручной перехват в 1 клик:** Оператор может переключить тумблер `[AI Active -> Manual Mode]` и ответить лично. ИИ засыпает для этого чата.


3. **RAG & Knowledge Base Manager:**
* Удобная загрузка прайс-листов, регламентов, файлов (PDF, DOCX, TXT, таблицы).
* Кнопка «Re-index» для моментального обновления базы знаний ИИ.


4. **Financial Operations (USDT & Escrow):**
* Журнал транзакций, проверка входящих платежей, кошелек для сбора средств.
* Настройка условий работы гарантов (комиссии, правила споров).


5. **Prompt Engine & Tone Control:**
* Редактирование правил поведения ИИ, уступчивости при торге, манеры общения.



---

## 4. Технологический стек

| Модуль | Технологии |
| --- | --- |
| **Backend & Bot Core** | Python 3.11+, FastAPI, Pyrogram / Telethon (для работы через личный/бизнес аккаунт), Celery + Redis |
| **AI Layer & LLM** | Google Gemini 1.5 / 2.0 Flash API, LangChain / LangGraph, Qdrant (Векторная БД) |
| **Blockchain Integration** | TronPy / TronGrid REST API (USDT TRC-20 Monitoring) |
| **Frontend (Web3 Panel)** | Next.js 14, React, Tailwind CSS, Three.js / React Flow (для визуализации графов нейросетей) |
| **Database & Cache** | PostgreSQL (пользователи, заказы, диалоги), Redis (сессии и очереди) |

---

## 5. Платежный сценарий и Escrow (Гарант)

```
[Клиент в Telegram] ──> "Хочу купить, какая цена?"
                              │
[AI Sales Agent]    ──> "Цена $150. Оплачиваем прямо на USDT TRC-20 или через Гаранта?"
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
   [Прямой платеж TRC-20]            [Сделка через Гаранта]
             │                                 │
  1. AI создает уникальный           1. AI через API генерирует
     TRC-20 кошелек.                    Escrow-сделку.
  2. Мониторинг сети Tron            2. Передает клиенту ссылку
     (TronGrid).                        и проверяет статус
  3. Оплата подтверждена ──> [Уведомление в CRM] <── Депозит внесен

```

---

## 6. План и этапы разработки

1. **Этап 1: Проектирование и Интеграция Telegram API (10 дней)**
* Настройка Pyrogram/Telethon, разворачивание PostgreSQL & Redis, интеграция Gemini Flash API.


2. **Этап 2: Мультиагентный движок & База знаний RAG (14 дней)**
* Настройка сценариев продаж, векторной базы Qdrant, автономного модуля фоллоу-апов.


3. **Этап 3: Крипто-модуль USDT TRC-20 + Escrow (8 дней)**
* Подключение TronGrid API, автоматическая генерация адресов, проверка подтверждений транзакций, интеграция гаранта.


4. **Этап 4: Web3 Админ-панель (14 дней)**
* Разработка футуристичного UI (Next.js), реализация 3D/2D графа агентов (Three.js), чата ручного перехвата и управления знаниями.


5. **Этап 5: Тестирование и Запуск (6 дней)**
* Нагрузочное тестирование, отработка редких сценариев (краевые случаи), сдача проекта.



*Сгенерированный PDF-файл ТЗ доступен для скачивания по ссылке выше.*