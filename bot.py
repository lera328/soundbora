#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import re
import tempfile
from typing import List

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp

# Настройка логгирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация бота
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8039626483:AAEuzawB20gusOwC38ME6lxAoIKsiBJAgpw")
SOUNDCLOUD_PLAYLIST_REGEX = r"https?://(?:(?:www\.)?soundcloud\.com/[^/]+/sets/[^/\s]+|(?:on\.)?soundcloud\.com/[A-Za-z0-9]+)"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    await update.message.reply_text(
        "Привет! Отправь мне ссылку на плейлист SoundCloud, и я скачаю все треки."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    await update.message.reply_text(
        "Как использовать бота:\n"
        "1. Отправьте ссылку на плейлист SoundCloud\n"
        "2. Дождитесь загрузки треков\n\n"
        "Пример ссылки: https://soundcloud.com/user/sets/playlist-name"
    )

# Удалены функции отмены загрузки для минималистичного интерфейса

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик входящих сообщений"""
    message_text = update.message.text

    # Проверяем URL плейлиста
    match = re.search(SOUNDCLOUD_PLAYLIST_REGEX, message_text)
    if not match:
        await update.message.reply_text("❌ Пожалуйста, отправьте корректную ссылку на SoundCloud плейлист.")
        return

    playlist_url = match.group(0)
    
    await update.message.reply_text(
        "⏳ Начинаю обработку плейлиста..."
    )

    try:
        track_count = await download_playlist(update, context, playlist_url)
        await update.message.reply_text(f"✅ Готово! Обработано треков: {track_count}")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def download_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                          playlist_url: str) -> int:
    """Загрузка плейлиста"""
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'extract_flat': False,
        'playlistend': 50,  # Лимит треков для безопасности
    }

    try:
        # Отправляем сообщение о начале получения информации
        info_msg = await update.message.reply_text("Получаю информацию о плейлисте...")
        
        # Получаем информацию о плейлисте
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            
            if not info or 'entries' not in info:
                await info_msg.edit_text("Не удалось получить информацию о плейлисте")
                raise Exception("Не удалось получить информацию о плейлисте")
            
            tracks = [t for t in info['entries'] if t]
            total_tracks = len(tracks)
            
            if not total_tracks:
                await info_msg.edit_text("Плейлист пуст или содержит только недоступные треки")
                raise Exception("Плейлист пуст")
            
            # Обновляем сообщение о количестве треков
            await info_msg.edit_text(f"Найдено треков: {total_tracks}. Начинаю загрузку...")
            
            track_count = 0
            for track_idx, track in enumerate(tracks):
                track_url = track.get('url', track.get('webpage_url'))
                if not track_url:
                    continue
                
                try:
                    # Отправляем уведомление о загрузке конкретного трека
                    track_title = track.get('title', 'Неизвестный трек')
                    await update.message.reply_text(f"Загрузка трека {track_idx+1}/{total_tracks}: {track_title}")
                    
                    # Загружаем трек
                    with yt_dlp.YoutubeDL(ydl_opts) as track_dl:
                        result = track_dl.extract_info(track_url, download=True)
                    
                    # Отправляем файл пользователю
                    if result and 'requested_downloads' in result:
                        for download in result['requested_downloads']:
                            filepath = download['filepath']
                            if os.path.exists(filepath):
                                await send_audio_file(update, context, filepath, track)
                                track_count += 1
                                os.remove(filepath)
                except yt_dlp.utils.DownloadError as e:
                    logger.error(f"Ошибка загрузки трека {track_idx+1}: {str(e)}")
                    await update.message.reply_text(f"\u26a0️ Ошибка загрузки трека {track_idx+1}/{total_tracks}: {str(e)[:100]}")
                    continue
                except Exception as e:
                    logger.error(f"Непредвиденная ошибка при загрузке трека {track_idx+1}: {str(e)}")
                    await update.message.reply_text(f"\u26a0️ Трек {track_idx+1}/{total_tracks} пропущен из-за ошибки")
                    continue
            
            return track_count
    except Exception as e:
        logger.error(f"Ошибка загрузки плейлиста: {str(e)}")
        raise

async def send_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                        filepath: str, track_info: dict):
    """Отправка аудиофайла пользователю"""
    title = track_info.get('title', 'Без названия')[:64]
    artist = track_info.get('uploader', 'Неизвестный исполнитель')[:64]
    
    with open(filepath, 'rb') as audio_file:
        await context.bot.send_audio(
            chat_id=update.effective_chat.id,
            audio=audio_file,
            title=title,
            performer=artist,
            caption=f"{artist} - {title}"
        )

def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))

    # Запуск бота
    application.run_polling()

if __name__ == "__main__":
    main()