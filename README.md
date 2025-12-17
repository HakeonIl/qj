# qj - Game Translator (게임번역)

A simple and lightweight game translation tool for managing multi-language support in games.

## Features

- ✨ Simple API for managing game text translations
- 🌍 Support for multiple languages (English, Korean, Japanese, and more)
- 💾 JSON-based translation file format
- 🎮 Easy integration with game projects
- 🔄 Dynamic language switching

## Installation

No external dependencies required! Just use Python 3.6+

```bash
git clone https://github.com/HakeonIl/qj.git
cd qj
```

## Quick Start

### Basic Usage

```python
from game_translator import GameTranslator

# Create a translator instance
translator = GameTranslator()

# Add translations
translator.add_translation("game.start", "en", "Start Game")
translator.add_translation("game.start", "ko", "게임 시작")
translator.add_translation("game.start", "ja", "ゲーム開始")

# Set language
translator.set_language("ko")

# Get translated text
print(translator.get_translation("game.start"))  # Output: 게임 시작
```

### Using Translation Files

```python
from game_translator import GameTranslator

# Load translations from JSON file
translator = GameTranslator()
translator.load_from_file("game_translations.json")

# Use translations
translator.set_language("ja")
print(translator.get_translation("game.start"))  # Output: ゲーム開始
```

## Running Examples

### Demo the translation tool:

```bash
python3 game_translator.py
```

### Run the example game:

```bash
python3 example_game.py
```

## Translation File Format

Translations are stored in JSON format:

```json
{
  "game.start": {
    "en": "Start Game",
    "ko": "게임 시작",
    "ja": "ゲーム開始"
  },
  "game.quit": {
    "en": "Quit",
    "ko": "종료",
    "ja": "終了"
  }
}
```

## API Reference

### GameTranslator Class

#### Methods

- `add_translation(key, language, text)` - Add a translation for a specific key and language
- `get_translation(key, language=None)` - Get translation for a key (uses current language if not specified)
- `set_language(language)` - Set the current active language
- `load_from_file(filename)` - Load translations from a JSON file
- `save_to_file(filename)` - Save translations to a JSON file
- `get_all_keys()` - Get all translation keys
- `get_supported_languages()` - Get all supported languages

## Supported Languages

The tool supports any language you add. Common examples include:

- `en` - English
- `ko` - Korean (한국어)
- `ja` - Japanese (日本語)
- `zh` - Chinese (中文)
- `es` - Spanish
- `fr` - French
- And more...

## Use Cases

- 🎮 Game localization
- 📱 Multi-language game menus
- 🌐 Internationalization (i18n) for indie games
- 🎯 Quick prototyping of multi-language game UIs

## License

MIT License

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests.

## Author

HakeonIl