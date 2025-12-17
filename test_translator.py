#!/usr/bin/env python3
"""
Simple tests for the game translator.
"""

from game_translator import GameTranslator
import os
import json


def test_basic_translation():
    """Test basic translation functionality."""
    translator = GameTranslator()
    translator.add_translation("test.key", "en", "English text")
    translator.add_translation("test.key", "ko", "한국어 텍스트")
    
    translator.set_language("en")
    assert translator.get_translation("test.key") == "English text", "English translation failed"
    
    translator.set_language("ko")
    assert translator.get_translation("test.key") == "한국어 텍스트", "Korean translation failed"
    
    print("✓ Basic translation test passed")


def test_missing_translation():
    """Test behavior when translation is missing."""
    translator = GameTranslator()
    translator.add_translation("test.key", "en", "English text")
    
    # Request translation for missing language
    result = translator.get_translation("test.key", "fr")
    assert result == "test.key", "Missing translation should return key"
    
    print("✓ Missing translation test passed")


def test_file_operations():
    """Test loading and saving translations."""
    translator = GameTranslator()
    translator.add_translation("file.test", "en", "File test")
    translator.add_translation("file.test", "ko", "파일 테스트")
    
    # Save to file
    test_file = "/tmp/test_translations.json"
    translator.save_to_file(test_file)
    
    # Load from file
    new_translator = GameTranslator()
    new_translator.load_from_file(test_file)
    
    assert new_translator.get_translation("file.test", "en") == "File test", "Loaded translation mismatch"
    assert new_translator.get_translation("file.test", "ko") == "파일 테스트", "Loaded Korean translation mismatch"
    
    # Clean up
    os.remove(test_file)
    
    print("✓ File operations test passed")


def test_get_all_keys():
    """Test getting all translation keys."""
    translator = GameTranslator()
    translator.add_translation("key1", "en", "Text 1")
    translator.add_translation("key2", "en", "Text 2")
    translator.add_translation("key3", "en", "Text 3")
    
    keys = translator.get_all_keys()
    assert len(keys) == 3, "Wrong number of keys"
    assert "key1" in keys, "key1 not found"
    assert "key2" in keys, "key2 not found"
    assert "key3" in keys, "key3 not found"
    
    print("✓ Get all keys test passed")


def test_supported_languages():
    """Test getting supported languages."""
    translator = GameTranslator()
    translator.add_translation("key1", "en", "English")
    translator.add_translation("key1", "ko", "한국어")
    translator.add_translation("key2", "ja", "日本語")
    
    languages = translator.get_supported_languages()
    assert "en" in languages, "English not in supported languages"
    assert "ko" in languages, "Korean not in supported languages"
    assert "ja" in languages, "Japanese not in supported languages"
    assert len(languages) == 3, "Wrong number of supported languages"
    
    print("✓ Supported languages test passed")


def test_load_game_translations():
    """Test loading the actual game translations file."""
    translator = GameTranslator()
    translator.load_from_file("game_translations.json")
    
    # Check some translations exist
    translator.set_language("en")
    assert translator.get_translation("game.start") == "Start Game"
    
    translator.set_language("ko")
    assert translator.get_translation("game.start") == "게임 시작"
    
    translator.set_language("ja")
    assert translator.get_translation("game.start") == "ゲーム開始"
    
    print("✓ Game translations file test passed")


def run_all_tests():
    """Run all tests."""
    print("\nRunning Game Translator Tests")
    print("=" * 50)
    
    try:
        test_basic_translation()
        test_missing_translation()
        test_file_operations()
        test_get_all_keys()
        test_supported_languages()
        test_load_game_translations()
        
        print("\n" + "=" * 50)
        print("✓ All tests passed successfully!")
        print("=" * 50 + "\n")
        return True
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}\n")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}\n")
        return False


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
