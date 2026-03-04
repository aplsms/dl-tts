# Defence Line TTS

Скрипт автоматично зчитує нові статті з RSS-стрічки сайту [defence-line.info](https://defence-line.info) та озвучує їх у форматі MP3 за допомогою Google Gemini TTS.

## Вимоги

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) (для кодування MP3)
- Gemini API ключ — отримати на [aistudio.google.com](https://aistudio.google.com/apikey)

## Встановлення

### 1. Встановіть ffmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

### 2. Встановіть залежності Python

```bash
pip install -r requirements.txt
```

### 3. Збережіть API ключ

Створіть файл конфігурації `~/.local/dl-audio.conf`:

```bash
mkdir -p ~/.local
echo 'API_KEY=ВАШ_GEMINI_API_КЛЮЧ' > ~/.local/dl-audio.conf
```

Права доступу (щоб ключ не читали інші користувачі):

```bash
chmod 600 ~/.local/dl-audio.conf
```

## Використання

```bash
python defence_line_tts_gemini.py
```

Скрипт перевірить RSS-стрічку, пропустить вже озвучені статті та збереже нові MP3-файли у папку `defence_line_audio_gemini/`.

## Налаштування

Відкрийте `defence_line_tts_gemini.py` та змініть константи на початку файлу:

| Параметр | За замовчуванням | Опис |
|---|---|---|
| `MAX_ARTICLES` | `1` | Кількість останніх статей для перевірки за один запуск |
| `OUTPUT_DIR` | `defence_line_audio_gemini` | Папка для збереження MP3 |
| `VOICE` | `Algenib` | Голос Gemini TTS |
| `MODEL` | `gemini-2.5-flash-preview-tts` | Модель Gemini |

### Доступні голоси

Деякі голоси Gemini TTS: `Algenib`, `Aoede`, `Charon`, `Fenrir`, `Kore`, `Leda`, `Orus`, `Puck`, `Schedar`, `Zephyr`.

## Автоматичний запуск (cron)

Щоб запускати скрипт автоматично, наприклад щогодини:

```bash
crontab -e
```

Додайте рядок:

```
0 * * * * /usr/bin/python3 /шлях/до/defence_line_tts_gemini.py >> /tmp/dl-tts.log 2>&1
```
