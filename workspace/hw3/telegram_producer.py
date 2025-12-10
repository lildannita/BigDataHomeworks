#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import signal
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict

# Telethon для Telegram API
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.types import Channel, User
from telethon.errors import ChannelPrivateError, FloodWaitError

# Kafka
from kafka import KafkaProducer
from kafka.errors import KafkaError

TELEGRAM_API_ID = os.environ.get("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH")
SESSION_NAME = "/app/hw3/tmp/telegram_session"  # Путь к файлу сессии

# Kafka
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = "telegram_messages"

# Каналы для мониторинга
CHANNEL_IDS = [
    "@toporlive",
    "@ecotopor",
    "@cybers",
    "@mosnews",
    "@moscowach",
    "@techmedia",
    "@exploitex",
    "@kreator",
    "@novosti_efir",
    "https://t.me/+ULjQI9CfYMI0OGQy"
]
# ID каналов из задания, но они не работают:
# CHANNEL_IDS = [
#     1050820672,
#     1149896996,
#     1101170442,
#     1036362176,
#     1310155678,
#     1001872252,
#     1054549314,
#     1073571855,
# ]

# Схема сообщения
@dataclass
class TelegramMessage:
    """
    Структура сообщения из Telegram-канала.
    Поля соответствуют данным, которые можно извлечь из события NewMessage в Telethon.
    """
    event_time: str              # ISO формат: "2025-12-06T21:30:45.123456"
    channel_id: int              # ID канала
    channel_name: Optional[str]  # Название канала
    message_id: int              # ID сообщения в канале
    user_id: Optional[int]       # ID отправителя (None для анонимных)
    username: Optional[str]      # @username отправителя
    first_name: Optional[str]    # Имя отправителя
    last_name: Optional[str]     # Фамилия отправителя
    text: str                    # Текст сообщения
    text_length: int             # Длина текста
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class TelegramKafkaProducer:
    """Класс для получения сообщений из Telegram и отправки в Kafka."""

    def __init__(self):
        # Проверка наличия нужных данных
        if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
            raise ValueError("Не заданы TELEGRAM_API_ID и/или TELEGRAM_API_HASH.")

        # Telegram клиент
        self.client = TelegramClient(
            SESSION_NAME,
            int(TELEGRAM_API_ID),
            TELEGRAM_API_HASH
        )

        # Kafka producer
        # acks='all' — ждём подтверждения от всех реплик
        # value_serializer — автоматическая сериализация в байты
        self.kafka_producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            acks='all',
            retries=3,
            value_serializer=lambda v: v.encode('utf-8'),
            key_serializer=lambda k: str(k).encode('utf-8') if k else None,
        )

        # Кэш названий каналов (id -> name)
        self.channel_names: Dict[int, str] = {}

        # Флаг для корректной остановки
        self.running = False

    async def get_channel_name(self, channel_id: int) -> str:
        """
        Получение названия канала по ID.
        (если канал недоступен — возвращает "Unknown")
        """
        if channel_id in self.channel_names:
            return self.channel_names[channel_id]
        try:
            entity = await self.client.get_entity(channel_id)
            name = getattr(entity, 'title', None) or getattr(entity, 'username', None) or "Unknown"
            self.channel_names[channel_id] = name
            return name
        except Exception as e:
            print(f"  Не удалось получить название канала {channel_id}: {e}")
            return "Unknown"

    async def join_channels(self) -> List[int]:
        """Подключение к заданным каналам."""
        joined = []
        for channel_id in CHANNEL_IDS:
            try:
                print(f"Подключение к каналу {channel_id}...")
                # Получаем entity канала
                channel = await self.client.get_entity(channel_id)
                # Присоединяемся (если ещё не участник)
                await self.client(JoinChannelRequest(channel))
                # Получаем и кэшируем название
                name = await self.get_channel_name(channel_id)
                print(f"  + Подключено: {name}")
                joined.append(channel_id)
            except ChannelPrivateError:
                print(f"  - Канал {channel_id} приватный")
            except FloodWaitError as e:
                print(f"  ? Rate limit, ожидание {e.seconds} сек...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                print(f"  - Ошибка подключения к {channel_id}: {e}")
        return joined

    async def handle_new_message(self, event):
        """Обработчик нового сообщения."""
        try:
            message = event.message
            chat = await event.get_chat()
            sender = await event.get_sender()

            # Извлекаем данные отправителя
            user_id = None
            username = None
            first_name = None
            last_name = None
            if sender:
                user_id = sender.id
                username = getattr(sender, 'username', None)
                first_name = getattr(sender, 'first_name', None)
                last_name = getattr(sender, 'last_name', None)
            # ID канала
            channel_id = chat.id
            if hasattr(chat, 'id'):
                # Telegram использует отрицательные ID для каналов в некоторых контекстах
                channel_id = abs(chat.id)
            # Название канала
            channel_name = await self.get_channel_name(channel_id)
            # Текст сообщения
            text = message.text or ""

            # Создаём объект сообщения
            msg = TelegramMessage(
                event_time=datetime.now(timezone.utc).isoformat(),
                channel_id=channel_id,
                channel_name=channel_name,
                message_id=message.id,
                user_id=user_id,
                username=username or f"user_{user_id}" if user_id else "anonymous",
                first_name=first_name,
                last_name=last_name,
                text=text,
                text_length=len(text),
            )

            # Отправляем в Kafka
            self.kafka_producer.send(
                KAFKA_TOPIC,
                key=str(user_id) if user_id else None, # для партиционирования по пользователю
                value=msg.to_json()
            )

            # Логируем
            display_name = username or first_name or f"user_{user_id}" or "anonymous"
            text_preview = text[:50] + "..." if len(text) > 50 else text
            print(f"[{channel_name}] {display_name}: {text_preview}")
        except Exception as e:
            print(f"Ошибка обработки сообщения: {e}")

    async def start(self):
        """Инициализация и запуск producer."""
        # Подключаемся к Telegram
        print("\nПодключение к Telegram API...")
        await self.client.start()
        me = await self.client.get_me()
        print(f"+ Авторизован как: {me.username or me.first_name}")

        # Подключаемся к каналам
        print("Подключение к каналам...")
        joined = await self.join_channels()
        print(f"+ Подключено каналов: {len(joined)}/{len(CHANNEL_IDS)}")

        if not joined:
            print("- Не удалось подключиться ни к одному каналу!")
            return False

        # Регистрируем обработчик новых сообщений
        @self.client.on(events.NewMessage(chats=joined))
        async def handler(event):
            await self.handle_new_message(event)

        print("=" * 60)
        print("Ожидание сообщений...")
        print("=" * 60)
        self.running = True
        return True

    async def run(self):
        """Запуск бесконечного цикла обработки сообщений."""
        if await self.start():
            await self.client.run_until_disconnected()

    def stop(self):
        """Корректное завершение работы."""
        print("Остановка producer...")
        self.running = False
        self.kafka_producer.flush()
        self.kafka_producer.close()
        print("+ Kafka producer закрыт")


def main():
    producer = TelegramKafkaProducer()
    # Обработка Ctrl+C
    def signal_handler(sig, frame):
        producer.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Запуск
    with producer.client:
        producer.client.loop.run_until_complete(producer.run())


if __name__ == "__main__":
    main()
