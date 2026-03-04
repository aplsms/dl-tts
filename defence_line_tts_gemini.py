import feedparser
import os
import re
import sys
import time
import json
import hashlib
from datetime import datetime
import argparse
import requests
from pydub import AudioSegment
from google import genai
from google.genai import types
from bs4 import BeautifulSoup

# === ЗАВАНТАЖЕННЯ API КЛЮЧА ===
_config_path = os.path.expanduser("~/.local/dl-audio.conf")
if not os.path.exists(_config_path):
    print(f"[ERROR] Файл конфігурації не знайдено: {_config_path}")
    print(f'[ERROR] Створіть файл з вмістом: API_KEY=ваш_ключ')
    sys.exit(1)
_config = {}
with open(_config_path) as _f:
    for _line in _f:
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _, _v = _line.partition('=')
            _config[_k.strip()] = _v.strip().strip('"').strip("'")
if 'API_KEY' not in _config:
    print(f"[ERROR] API_KEY не знайдено у {_config_path}")
    sys.exit(1)
API_KEY = _config['API_KEY']

# === НАЛАШТУВАННЯ СКРИПТУ ===
RSS_URL = "https://defence-line.info/?feed=rss2"
OUTPUT_DIR = "defence_line_audio_gemini"
# Модель та голос
MODEL = "gemini-2.5-flash-preview-tts"
VOICE = "Algenib"
# Максимальна кількість нових статей для обробки за один запуск
MAX_ARTICLES = 5

# Ініціалізація клієнта Gemini
client = genai.Client(api_key=API_KEY)

def clean_html(html_content):
    """Видаляє HTML-теги та зайві пробіли з тексту статті."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def sanitize_filename(filename):
    """Створює безпечне ім'я файлу з заголовка."""
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename[:100].strip()


def format_pubdate_from_entry(entry):
    """Return string YY-MM-DD_hh:mm from feed entry or now as fallback."""
    # try structured time from feedparser
    pp = None
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        pp = entry.published_parsed
    elif 'published_parsed' in entry and entry['published_parsed']:
        pp = entry['published_parsed']
    if pp:
        try:
            ts = time.mktime(pp)
            dt = datetime.fromtimestamp(ts)
            return dt.strftime('%y-%m-%d_%H:%M')
        except Exception:
            pass

    # try parsing published string as ISO
    pubstr = entry.get('published') if 'published' in entry else entry.get('updated') if 'updated' in entry else None
    if pubstr:
        try:
            dt = datetime.fromisoformat(pubstr.replace('Z', '+00:00'))
            return dt.strftime('%y-%m-%d_%H:%M')
        except Exception:
            pass

    return datetime.now().strftime('%y-%m-%d_%H:%M')


def format_pubdate_from_soup(soup):
    """Try to extract publication date from HTML meta tags, fallback to now."""
    meta_props = [
        ("property", "article:published_time"),
        ("property", "og:published_time"),
        ("name", "pubdate"),
        ("name", "publishdate"),
        ("itemprop", "datePublished"),
        ("name", "date"),
    ]
    for attr, val in meta_props:
        m = soup.find('meta', attrs={attr: val})
        if m and m.get('content'):
            c = m.get('content')
            try:
                dt = datetime.fromisoformat(c.replace('Z', '+00:00'))
                return dt.strftime('%y-%m-%d_%H:%M')
            except Exception:
                # try simple YYYY-MM-DD prefix
                try:
                    dt = datetime.strptime(c[:10], '%Y-%m-%d')
                    return dt.strftime('%y-%m-%d_%H:%M')
                except Exception:
                    continue
    return datetime.now().strftime('%y-%m-%d_%H:%M')

def download_and_tts():
    # Створюємо папку для аудіо
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"[INFO] Створено папку: {OUTPUT_DIR}")
    # Завантажуємо індекс оброблених статей
    processed_db_path = os.path.join(OUTPUT_DIR, "processed.json")
    if os.path.exists(processed_db_path):
        try:
            with open(processed_db_path, "r", encoding="utf-8") as _f:
                processed = json.load(_f)
        except Exception:
            processed = {}
    else:
        processed = {}

    print(f"[INFO] Отримання даних з RSS: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)

    if not feed.entries:
        print("[ERROR] Не вдалося отримати записи з RSS.")
        return

    # Обробляємо лише останні статті
    entries_to_process = feed.entries[:MAX_ARTICLES]
    print(f"[INFO] Буде перевірено останніх статей: {len(entries_to_process)}")

    for entry in entries_to_process:
        title = entry.title

        # Унікальний ідентифікатор статті: переважно 'id' або 'link', інакше хеш від заголовка+дати
        entry_id = None
        if hasattr(entry, 'id') and entry.id:
            entry_id = entry.id
        elif 'id' in entry and entry['id']:
            entry_id = entry['id']
        elif 'link' in entry and entry['link']:
            entry_id = entry['link']
        else:
            # Використовуємо короткий хеш як fallback
            digest = hashlib.sha1((title + str(entry.get('published', ''))).encode('utf-8')).hexdigest()
            entry_id = f"title-hash:{digest}"

        # Якщо стаття вже була оброблена (збережено в processed.json), пропускаємо
        if entry_id in processed:
            print(f"[SKIP] Уже оброблено (index): {title}")
            continue

        # Отримуємо контент статті
        content = ""
        if 'content' in entry:
            content = entry.content[0].value
        elif 'summary' in entry:
            content = entry.summary

        clean_text = clean_html(content)
        # Додаємо заголовок до тексту для озвучування
        full_speech_text = f"{title}. {clean_text}"

        # Формування шляху до файлу з префіксом pubDate
        pubdate_prefix = format_pubdate_from_entry(entry)
        filename = f"{pubdate_prefix}_{sanitize_filename(title)}.mp3"
        filepath = os.path.join(OUTPUT_DIR, filename)

        # Якщо файл вже існує, пропускаємо статтю
        if os.path.exists(filepath):
            print(f"[SKIP] Вже озвучено: {title}")
            # Записуємо в індекс, щоб уникнути подальших дублювань
            processed[entry_id] = filename
            try:
                with open(processed_db_path, "w", encoding="utf-8") as _f:
                    json.dump(processed, _f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            continue

        print(f"[PROCESS] Озвучування Gemini ({VOICE}): {title}")
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=full_speech_text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=VOICE,
                            )
                        )
                    ),
                ),
            )

            audio_data = response.candidates[0].content.parts[0].inline_data.data
            AudioSegment(
                data=audio_data,
                sample_width=2,
                frame_rate=24000,
                channels=1,
            ).export(filepath, format="mp3", bitrate="64k")
            print(f"[SUCCESS] Збережено: {filename}")
            # Додаємо запис до індексу оброблених статей
            processed[entry_id] = filename
            try:
                with open(processed_db_path, "w", encoding="utf-8") as _f:
                    json.dump(processed, _f, ensure_ascii=False, indent=2)
            except Exception:
                print(f"[WARN] Не вдалося записати індекс: {processed_db_path}")

            # Невелика пауза між запитами
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR] Помилка при обробці '{title}': {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TTS for Defence Line using Gemini")
    parser.add_argument("--url", help="URL of the article to TTS")
    parser.add_argument("--max", type=int, help="Max articles to process from RSS", default=MAX_ARTICLES)
    args = parser.parse_args()
    # allow overriding MAX_ARTICLES via CLI
    if args.max:
        MAX = args.max
    if args.url:
        # Fetch the URL and generate TTS for it
        def tts_from_url(url):
            # ensure output dir and processed db
            if not os.path.exists(OUTPUT_DIR):
                os.makedirs(OUTPUT_DIR)
                print(f"[INFO] Створено папку: {OUTPUT_DIR}")
            processed_db_path = os.path.join(OUTPUT_DIR, "processed.json")
            if os.path.exists(processed_db_path):
                try:
                    with open(processed_db_path, "r", encoding="utf-8") as _f:
                        processed = json.load(_f)
                except Exception:
                    processed = {}
            else:
                processed = {}

            try:
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
            except Exception as e:
                print(f"[ERROR] Не вдалося завантажити URL: {e}")
                return

            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else url
            # Use main article content if available, otherwise whole page
            article_tag = soup.find('article')
            if article_tag:
                content_html = str(article_tag)
            else:
                # Try common container classes
                main = soup.find(attrs={"class": re.compile(r"(post|article|entry|content)", re.I)})
                content_html = str(main) if main else resp.text

            clean_text = clean_html(content_html)
            full_speech_text = f"{title}. {clean_text}"

            # Determine publication date (try meta tags), entry id is URL
            entry_id = url

            # filename with pubDate prefix
            pubdate_prefix = format_pubdate_from_soup(soup)
            filename = f"{pubdate_prefix}_{sanitize_filename(title)}.mp3"
            filepath = os.path.join(OUTPUT_DIR, filename)

            if entry_id in processed:
                print(f"[SKIP] Уже оброблено (index): {title}")
                return
            if os.path.exists(filepath):
                print(f"[SKIP] Вже озвучено: {title}")
                processed[entry_id] = filename
                try:
                    with open(processed_db_path, "w", encoding="utf-8") as _f:
                        json.dump(processed, _f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                return

            print(f"[PROCESS] Озвучування Gemini ({VOICE}): {title}")
            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=full_speech_text,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=VOICE,
                                )
                            )
                        ),
                    ),
                )

                audio_data = response.candidates[0].content.parts[0].inline_data.data
                AudioSegment(
                    data=audio_data,
                    sample_width=2,
                    frame_rate=24000,
                    channels=1,
                ).export(filepath, format="mp3", bitrate="64k")
                print(f"[SUCCESS] Збережено: {filename}")
                processed[entry_id] = filename
                try:
                    with open(processed_db_path, "w", encoding="utf-8") as _f:
                        json.dump(processed, _f, ensure_ascii=False, indent=2)
                except Exception:
                    print(f"[WARN] Не вдалося записати індекс: {processed_db_path}")
            except Exception as e:
                print(f"[ERROR] Помилка при обробці '{title}': {e}")

        tts_from_url(args.url)
    else:
        download_and_tts()
    print("[DONE] Роботу завершено.")
