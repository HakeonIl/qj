#!/usr/bin/env python3
"""
Game Translation Tool
A simple tool to translate game text between languages.
"""

import json
import sys
from typing import Dict, List


class GameTranslator:
    """
    A simple game translator that manages translations for game text.
    """
    
    def __init__(self):
        self.translations: Dict[str, Dict[str, str]] = {}
        self.current_language = "en"
    
    def add_translation(self, key: str, language: str, text: str):
        """
        Add a translation for a specific key and language.
        
        Args:
            key: The unique identifier for the text
            language: The language code (e.g., 'en', 'ko', 'ja')
            text: The translated text
        """
        if key not in self.translations:
            self.translations[key] = {}
        self.translations[key][language] = text
    
    def get_translation(self, key: str, language: str = None) -> str:
        """
        Get a translation for a specific key and language.
        
        Args:
            key: The unique identifier for the text
            language: The language code (defaults to current_language)
        
        Returns:
            The translated text, or the key if translation not found
        """
        if language is None:
            language = self.current_language
        
        if key in self.translations and language in self.translations[key]:
            return self.translations[key][language]
        return key
    
    def set_language(self, language: str):
        """Set the current language."""
        self.current_language = language
    
    def load_from_file(self, filename: str):
        """
        Load translations from a JSON file.
        
        Args:
            filename: Path to the JSON file
        """
        with open(filename, 'r', encoding='utf-8') as f:
            self.translations = json.load(f)
    
    def save_to_file(self, filename: str):
        """
        Save translations to a JSON file.
        
        Args:
            filename: Path to the JSON file
        """
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.translations, f, ensure_ascii=False, indent=2)
    
    def get_all_keys(self) -> List[str]:
        """Get all translation keys."""
        return list(self.translations.keys())
    
    def get_supported_languages(self) -> List[str]:
        """Get all supported languages across all translations."""
        languages = set()
        for key_translations in self.translations.values():
            languages.update(key_translations.keys())
        return sorted(list(languages))


def main():
    """Main function for CLI usage."""
    translator = GameTranslator()
    
    # Example translations
    translator.add_translation("game.start", "en", "Start Game")
    translator.add_translation("game.start", "ko", "게임 시작")
    translator.add_translation("game.start", "ja", "ゲーム開始")
    
    translator.add_translation("game.quit", "en", "Quit")
    translator.add_translation("game.quit", "ko", "종료")
    translator.add_translation("game.quit", "ja", "終了")
    
    translator.add_translation("game.settings", "en", "Settings")
    translator.add_translation("game.settings", "ko", "설정")
    translator.add_translation("game.settings", "ja", "設定")
    
    translator.add_translation("game.score", "en", "Score")
    translator.add_translation("game.score", "ko", "점수")
    translator.add_translation("game.score", "ja", "スコア")
    
    # Demonstrate translations
    print("Game Translation Tool Demo")
    print("=" * 40)
    
    for lang in ["en", "ko", "ja"]:
        translator.set_language(lang)
        print(f"\nLanguage: {lang}")
        print(f"  {translator.get_translation('game.start')}")
        print(f"  {translator.get_translation('game.quit')}")
        print(f"  {translator.get_translation('game.settings')}")
        print(f"  {translator.get_translation('game.score')}")
    
    # Note: Not saving to avoid overwriting the comprehensive translation file
    # To save these demo translations, uncomment the line below:
    # translator.save_to_file("demo_translations.json")
    print("\n\n(Demo complete - translations not saved to preserve existing file)")


if __name__ == "__main__":
    main()
