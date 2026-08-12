# Настройка Amazon Ads API для дашборда CleanWin

Пошаговая инструкция подключения Amazon Advertising API (реклама Sponsored Products на Amazon.be) к дашборду `marketplace_dashboard.html`. Записано по факту прохождения процесса 12.08.2026.

## Контекст

- Продавец: **CinderellaMagicMop** (Seller Central), бренд листингов — **Quick Wish** (в процессе ребрендинга на CleanWin®).
- Account ID в Amazon Ads: `AXAPTQN0UM6V1`
- Маркетплейс: Belgium
- Активные кампании на момент настройки: `NL_Manual_Exact`, `KW MOP`, `AUTO for Mop`

Это **отдельный API от SP-API** (который уже подключен для заказов/финансов). SP-API credentials (`amazon_credentials.json`) не подходят для рекламы — нужен отдельный LWA Security Profile и отдельный refresh token со scope `advertising::campaign_management`.

## Шаг 1 — подтверждение, что реклама реально тратит деньги

Прежде чем регистрировать API, проверили в `advertising.amazon.com` → Campaigns, что кампании активны и есть реальный расход (не нулевые). На 1–11 авг. 2026: 649 показов, 20 кликов, 4 покупки, €11.05 расход, €92.52 продаж, ACOS 11.94%. Так как расход реальный, а дашборд его не видит — есть смысл подключать API.

## Шаг 2 — где искать доступ внутри Ads-консоли

`Amazon Ads → Administration → Account access and settings → Third-party applications` — здесь **только список уже авторизованных приложений** (на момент настройки был пуст: "No third-party applications found"). Это НЕ место для регистрации нового API-доступа — оно только для просмотра/отзыва.

## Шаг 3 — подача заявки на доступ к Amazon Ads API

Заявка подаётся на отдельной странице (форма "Amazon Ads API registration"), доступной через:
`https://advertising.amazon.com/about-api` → кнопка **"Request API access"** → категория **"Direct advertiser"** → `https://advertising.amazon.com/partner-network/register-api`

### Заполненные поля формы (12.08.2026):

**Company information**
| Поле | Значение |
|---|---|
| Company legal name | Oleksandr Pelykh |
| Company website | cleanwin.eu |
| Country of registration | Belgium |

**Account information**
| Поле | Значение |
|---|---|
| Brand name | Quick Wish *(бренд аккаунта на момент заявки; обновить на CleanWin после завершения ребрендинга)* |
| Countries | ✅ Belgium, ✅ Netherlands |

**Amazon Ads API use**
| Поле | Значение |
|---|---|
| Relationship | Amazon seller and plan to use Amazon Ads API for my own business |
| What specific solution(s) do you plan to build | Internal reporting dashboard that pulls Sponsored Products campaign performance (spend, sales, ACoS, clicks) for our own Amazon.be advertising account, combined with our existing bol.com sales dashboard for unified reporting. |
| Which advertising processes are you aiming to automate | Automated daily reporting and monitoring of ad spend, sales, and ACoS per campaign. No bid or campaign management automation planned at this stage — reporting only. |

**Data and access (scope)**
- ✅ Advertising — Manage advertising campaigns and creative, and receive advertising reporting metrics
- ☐ Data provider — не нужен

Согласие с Amazon API License Agreement и Data Protection Policy — отмечено. Отправлено на review (**Submit for review**).

## Шаг 4 — ожидание одобрения

Amazon рассматривает заявку (не мгновенно). Статус можно проверять там же, в личном кабинете разработчика.

## Шаг 5 (после одобрения) — LWA Security Profile

Создать/использовать Security Profile на `developer.amazon.com`, привязанный к аккаунту Amazon Ads (это отдельно от Solution Provider Portal, который использовался для SP-API).

## Шаг 6 (после одобрения) — OAuth-авторизация с scope рекламы

Через LWA OAuth URL с параметром `scope=advertising::campaign_management profile`, войти под `CinderellaMagicMop`, подтвердить доступ → получить authorization code → обменять на `access_token` + `refresh_token` (новый, отдельный от SP-API токена).

## Шаг 7 (после одобрения) — получить Profile ID

`GET https://advertising-api-eu.amazon.com/v2/profiles` с заголовками `Authorization: Bearer <access_token>` и `Amazon-Advertising-API-ClientId: <client_id>` → найти профиль с `countryCode: BE`.

## Шаг 8 (после одобрения) — скрипт ежедневного сбора данных

Написать `update_amazon_ads.py`:
- Reporting API v3 (асинхронные отчёты) — запрос отчёта по кампаниям Sponsored Products (spend, sales, clicks, ACoS) за нужный период.
- Сохранять в JSON, аналогично `bol_cache.json` — с историей по дням, чтобы дашборд мог фильтровать по произвольному периоду.
- Подключить к Task Scheduler, аналогично `update_dashboard.py`.

## Шаг 9 (после одобрения) — обновление дашборда

- Карточка "Реклама Amazon" — читать из новых данных, с фильтром по периоду (сейчас всегда €0.00, т.к. Ads API не подключен).
- Добавить таблицу "Кампании Amazon Ads" (аналог существующей таблицы "Кампании Bol Ads").
- Добавить ACoS Amazon как отдельную метрику.

---
*Статус на 12.08.2026: заявка успешно отправлена (Success — "Amazon Ads API request has been successfully submitted"). Amazon обещал ответ по email в течение 72 часов (ожидаем к ~15.08.2026). Шаги 1–4 выполнены, ожидаем одобрения для продолжения (шаги 5–9).*
