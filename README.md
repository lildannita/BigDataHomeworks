# Выполнение домашних заданий по дисциплине "Методы обработки больлших данных"

Репозиторий содержит окружение и ноутбуки с результатами выполнения домашних работ.

---
## Структура репозитория

- `Dockerfile` — образ с Python + Spark + Jupyter.
- `docker-compose.yml` — запуск контейнеров `spark-app` и `kafka`.
- `requirements.txt` — Python-зависимости.
- `.env.example` — пример файла окружения.
- `workspace/` — рабочая директория с Jupyter-ноутбуками домашних работ (монтируется в контейнер как `/app`).

---
## Подготовка окружения

1. Установить **Docker** и **Docker Compose**.
2. Клонировать этот репозиторий и перейти в его каталог.
3. Создать файл окружения на основе примера:

  ```bash
  cp .env.example .env
  ```

4. Отредактировать `.env` при необходимости:

   * `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` — **обязательны только для воспроизведения ДЗ №3** (для остальных заданий можно оставить пустыми).
   * `KAFKA_BOOTSTRAP_SERVERS` по умолчанию — `kafka:9092`.
   * `SPARK_DRIVER_MEMORY`, `SPARK_EXECUTOR_MEMORY` — настройки памяти Spark.

---
## Сборка и запуск контейнеров

```bash
docker compose up --build -d
```

   Будут подняты два контейнера:

   * `kafka` — брокер Kafka.
   * `spark-app` — Spark + Jupyter Lab.

---
## Доступ к Jupyter Lab

1. После запуска открыть в браузере:

   ```
   http://localhost:8888
   ```

2. Токен/пароль отключены, вход без авторизации.

3. Корневая директория Jupyter: `/app` (локально это соответствует каталогу `workspace/` репозитория).

Ноутбуки домашних заданий находятся внутри `workspace/hw{номер}`.

---

## Воспроизведение ДЗ №3 (Telegram + Kafka + Spark)

Для корректного запуска третьего домашнего задания требуется:

1. Указать Telegram API-ключи в `.env`:

   ```env
   TELEGRAM_API_ID=ВАШ_ID
   TELEGRAM_API_HASH=ВАШ_HASH
   ```

   Значения берутся в разделе **API development tools** на сайте Telegram (my.telegram.org).

2. Перезапустить контейнеры (если `.env` был изменён):

   ```bash
   docker compose up -d
   ```

3. Поднять Jupyter (он уже работает в контейнере `spark-app`) и открыть ноутбук третьего задания в Jupyter по адресу `http://localhost:8888`.

4. **Отдельным процессом** запустить Telegram Producer внутри контейнера `spark-app`:

   ```bash
   docker exec -it spark-app python /app/hw3/telegram_producer.py
   ```

> **Примечание**
>
> Это задание можно полностью воспроизвести **без использования Telegram**.  
> В ноутбуке реализован **собственный генератор сообщений**, который отправляет данные в Kafka, поэтому:
>
> - указывать `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` в `.env` **не обязательно**;
> - не нужно запускать дополнительный процесс  
>   `docker exec -it spark-app python /app/hw3/telegram_producer.py`.
   
---

## Полезные команды

* Просмотр логов:

  ```bash
  docker compose logs -f spark-app
  docker compose logs -f kafka
  ```

* Остановить и удалить контейнеры:

  ```bash
  docker compose down
  ```

* Полная пересборка образа:

  ```bash
  docker compose build --no-cache
  docker compose up -d
  ```
