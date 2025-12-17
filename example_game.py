#!/usr/bin/env python3
"""
Example game using the translation system.
"""

from game_translator import GameTranslator


class SimpleGame:
    """A simple example game demonstrating translation usage."""
    
    def __init__(self, language="en"):
        self.translator = GameTranslator()
        self.translator.load_from_file("game_translations.json")
        self.translator.set_language(language)
        self.score = 0
        self.level = 1
    
    def show_menu(self):
        """Display the game menu."""
        print("\n" + "=" * 40)
        print(f"  {self.translator.get_translation('game.start')}")
        print(f"  {self.translator.get_translation('game.settings')}")
        print(f"  {self.translator.get_translation('game.quit')}")
        print("=" * 40)
    
    def show_game_status(self):
        """Display current game status."""
        print(f"\n{self.translator.get_translation('game.score')}: {self.score}")
        print(f"{self.translator.get_translation('game.level')}: {self.level}")
    
    def change_language(self, language):
        """Change the game language."""
        self.translator.set_language(language)
        print(f"\nLanguage changed to: {language}")


def main():
    """Demonstrate the game with different languages."""
    print("Game Translation Demo")
    print("=" * 40)
    
    # English version
    print("\n\n--- English Version ---")
    game_en = SimpleGame("en")
    game_en.show_menu()
    game_en.score = 1000
    game_en.level = 5
    game_en.show_game_status()
    
    # Korean version
    print("\n\n--- Korean Version (한국어) ---")
    game_ko = SimpleGame("ko")
    game_ko.show_menu()
    game_ko.score = 1000
    game_ko.level = 5
    game_ko.show_game_status()
    
    # Japanese version
    print("\n\n--- Japanese Version (日本語) ---")
    game_ja = SimpleGame("ja")
    game_ja.show_menu()
    game_ja.score = 1000
    game_ja.level = 5
    game_ja.show_game_status()
    
    # Language switching demo
    print("\n\n--- Language Switching Demo ---")
    game = SimpleGame("en")
    for lang in ["en", "ko", "ja"]:
        game.change_language(lang)
        game.show_menu()


if __name__ == "__main__":
    main()
