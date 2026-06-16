# Настройка автообновления дашборда (GitHub Pages)

## Как это работает

```
Каждое утро в 08:00 (Task Scheduler):
  update_dashboard.py
    → получает данные из bol.com API
    → обновляет marketplace_dashboard.html
    → git push → GitHub Pages
    
Владелец открывает ссылку на телефоне/ноуте → видит свежие данные ✅
```

---

## Шаг 1 — Смените Client Secret на bol.com

⚠️ **Обязательно!** Старый секрет виден в истории чата.

1. Войдите на [developer.bol.com](https://developer.bol.com)
2. Ваше приложение → **Credentials** → **Rotate secret**
3. Скопируйте новый секрет

Откройте `update_dashboard.py`, найдите и замените:
```python
CLIENT_SECRET = "ВСТАВЬТЕ_НОВЫЙ_СЕКРЕТ_ЗДЕСЬ"
```

---

## Шаг 2 — Создайте GitHub-репозиторий

1. Зайдите на [github.com](https://github.com) → **New repository**
2. Название: `marketplace-dashboard` (или любое другое)
3. Visibility: **Private** (данные бизнеса — лучше приватный)
4. Нажмите **Create repository**

> ⚠️ Приватный репозиторий + GitHub Pages требует **GitHub Pro** (~$4/мес).
> Если хотите бесплатно — сделайте репозиторий **Public**
> (дашборд без PII-данных, только агрегированная выручка — это допустимо).

---

## Шаг 3 — Инициализируйте git в папке CleanWin

Откройте **Command Prompt** и выполните (замените URL на свой из GitHub):

```cmd
cd C:\Users\kanur\Documents\Cowork\CleanWin

git init
git add marketplace_dashboard.html
git commit -m "initial dashboard"
git branch -M main
git remote add origin https://github.com/ВАШ_ЛОГИН/marketplace-dashboard.git
git push -u origin main
```

---

## Шаг 4 — Включите GitHub Pages

1. Откройте репозиторий на GitHub
2. **Settings** → **Pages**
3. Source: **Deploy from a branch**
4. Branch: **main** / **(root)**
5. Нажмите **Save**

Через ~1 минуту появится ссылка вида:
```
https://ВАШ_ЛОГИН.github.io/marketplace-dashboard/marketplace_dashboard.html
```

Отправьте эту ссылку владельцу бизнеса — он добавит в закладки.

---

## Шаг 5 — Настройте аутентификацию git (один раз)

Чтобы скрипт мог делать `git push` без ввода пароля:

1. На GitHub: **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. **Generate new token** → отметьте `repo` → **Generate**
3. Скопируйте токен

В Command Prompt выполните (замените данные):
```cmd
git config --global credential.helper store
```
Затем выполните любой `git push` вручную — введите логин GitHub и токен вместо пароля. После этого git запомнит.

---

## Шаг 6 — Проверьте скрипт вручную

```cmd
cd C:\Users\kanur\Documents\Cowork\CleanWin
python update_dashboard.py
```

Ожидаемый вывод:
```
====================================================
Обновление дашборда — 16.06.2026 08:00
====================================================
✅ Токен получен
🚚 Отгрузки...
...
✅ Готово! Дашборд обновлён

🚀 Публикуем на GitHub Pages...
  ✅ Опубликовано! Страница обновится через ~1 минуту.
```

---

## Шаг 7 — Настройте Windows Task Scheduler

1. **Win + R** → `taskschd.msc` → Enter
2. **Create Basic Task...**
3. Name: `Обновление дашборда bol.com`
4. Trigger: **Daily**, время **08:00**
5. Action: **Start a program**
   - Program: `python`
   - Arguments: `C:\Users\kanur\Documents\Cowork\CleanWin\update_dashboard.py`
6. **Finish**

---

## Итог

| Кто | Что делает |
|-----|-----------|
| Task Scheduler (ваш ноут) | Запускает скрипт каждое утро в 08:00 |
| update_dashboard.py | Обновляет HTML + делает git push |
| GitHub Pages | Публикует страницу в интернете |
| Владелец бизнеса | Открывает ссылку на телефоне — видит свежие данные |

> **Важно:** ноут должен быть включён в 08:00 и иметь интернет.
> Если ноут был выключен — запустите скрипт вручную когда включите.

---

## Структура файлов

```
CleanWin/
├── marketplace_dashboard.html   ← дашборд (публикуется на GitHub Pages)
├── update_dashboard.py          ← скрипт автообновления
└── setup_autorun.md             ← эта инструкция
```
