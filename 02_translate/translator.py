import os
import json
import re
import time
import asyncio
import aiohttp
import argparse
from typing import List, Dict, Any, Optional

class Translator:
    def __init__(self, config_path: str = "trans4/config/config.json", base_path: str = "trans4"):
        self.base_path = base_path
        self.config = self._load_config(config_path)
        self.client_session: Optional[aiohttp.ClientSession] = None
        self.speech_patterns = self._load_speech_patterns()
        self.glossary = self._load_glossary()
        self.prompt_template = self._load_prompt_template()
        self.separator = "␟"  # Unit Separator (U+241F)

    def _load_config(self, path: str) -> Dict[str, Any]:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_speech_patterns(self) -> str:
        path = os.path.join(self.base_path, "config/character_speech_patterns.json")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.dumps(json.load(f), ensure_ascii=False, indent=2)
        except FileNotFoundError:
            return "{}"

    def _load_glossary(self) -> str:
        path = os.path.join(self.base_path, "config/glossary.json")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                glossary = json.load(f)
                
                # Check for "고정_번역" (Fixed Translations) structure
                glossary_list = []
                if isinstance(glossary, dict):
                     # Handle { "고정_번역": { "key": "value", ... } }
                     fixed_trans = glossary.get("고정_번역", {})
                     for k, v in fixed_trans.items():
                         glossary_list.append(f"{k} -> {v}")
                         
                     # Handle "번역_안함" if necessary
                     no_trans = glossary.get("번역_안함", [])
                     for k in no_trans:
                         glossary_list.append(f"{k} -> {k} (Do Not Translate)")

                elif isinstance(glossary, list):
                    # Handle list of dicts: [{ "original": "...", "translated": "..." }, ...]
                    for item in glossary:
                        if isinstance(item, dict) and 'original' in item and 'translated' in item:
                            glossary_list.append(f"{item['original']} -> {item['translated']}: {item.get('notes', '')}")
                
                return "\n".join(glossary_list)
        except FileNotFoundError:
            return ""

    def _load_prompt_template(self) -> str:
        path = os.path.join(self.base_path, "02_translate/prompt_base_v2.md")
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    async def _get_client_session(self) -> aiohttp.ClientSession:
        if self.client_session is None or self.client_session.closed:
            self.client_session = aiohttp.ClientSession()
        return self.client_session

    async def close(self):
        if self.client_session:
            await self.client_session.close()

    def _construct_prompt(self, chunk_list: List[str]) -> str:
        # Convert list to JSON string for the prompt
        chunk_text = json.dumps(chunk_list, ensure_ascii=False, indent=2)
        return self.prompt_template.format(
            glossary_text=self.glossary,
            speech_patterns_text=self.speech_patterns
        ) + "\n\n**JSON Array to Translate:**\n```json\n" + chunk_text + "\n```"

    async def translate_chunk(self, chunk: List[Dict[str, Any]], attempt: int = 1) -> List[Dict[str, Any]]:
        """
        Translates a list of JSON objects (a chunk) using the optimized array format.
        """
        model_key = self.config.get("translator_model", "deepseek")
        model_config = self.config["models"][model_key]
        
        # 1. Transform to Optimized Format (Speaker␟Text)
        optimized_input = []
        for item in chunk:
            speaker = item.get('speaker', '') or ''
            text = item.get('text', '')
            optimized_input.append(f"{speaker}{self.separator}{text}")

        prompt = self._construct_prompt(optimized_input)

        # Max retries handling
        max_retries = 3
        if attempt > max_retries:
            print(f"❌ Max retries exceeded for chunk.")
            return []

        try:
            response_text = await self._call_llm(model_config, prompt)
            translated_lines_raw = self._parse_response(response_text)
            
            # 2. Reconstruct & Validate
            reconstructed_chunk = self._reconstruct_chunk(chunk, translated_lines_raw)
            
            if reconstructed_chunk and self._validate_translation(chunk, reconstructed_chunk):
                return reconstructed_chunk
            else:
                print(f"⚠️ Validation failed (Attempt {attempt}). Retrying...")
                return await self.translate_chunk(chunk, attempt + 1)

        except Exception as e:
            print(f"🔥 Error in translation (Attempt {attempt}): {e}")
            return await self.translate_chunk(chunk, attempt + 1)

    async def _call_llm(self, model_config: Dict[str, Any], prompt: str) -> str:
        api_key = model_config["api_key"]
        endpoint = model_config["endpoint"] + "/chat/completions"
        model_name = model_config["model_name"]
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are a professional game translator."},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.config["translation_settings"].get("temperature", 0.3),
            "stream": False
        }

        session = await self._get_client_session()
        async with session.post(endpoint, headers=headers, json=payload) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"API Error {resp.status}: {error_text}")
            
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_response(self, response_text: str) -> List[str]:
        """
        Extracts the JSON array of strings from the LLM response.
        """
        # Remove markdown code blocks if present
        cleaned_text = re.sub(r'```json\s*', '', response_text)
        cleaned_text = re.sub(r'```\s*', '', cleaned_text)
        
        try:
            # Try to find the JSON array in the text
            start_idx = cleaned_text.find('[')
            end_idx = cleaned_text.rfind(']')
            if start_idx != -1 and end_idx != -1:
                json_str = cleaned_text[start_idx:end_idx+1]
                return json.loads(json_str)
            else:
                # Fallback: try parsing the whole text
                return json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            print(f"⚠️ Failed to parse JSON response: {e}")
            return []

    def _reconstruct_chunk(self, original_chunk: List[Dict[str, Any]], translated_lines_raw: List[str]) -> Optional[List[Dict[str, Any]]]:
        """
        Merges the translated strings back into the original JSON objects.
        """
        if len(original_chunk) != len(translated_lines_raw):
            print(f"❌ Length mismatch during reconstruction. Original: {len(original_chunk)}, Translated: {len(translated_lines_raw)}")
            return None

        new_chunk = []
        for i, (orig, trans_str) in enumerate(zip(original_chunk, translated_lines_raw)):
            # Create a copy to avoid modifying the original in case of retry
            new_item = orig.copy()
            
            parts = trans_str.split(self.separator)
            
            if len(parts) < 2:
                # Separator missing!
                print(f"❌ Separator '{self.separator}' missing in line {i}: {trans_str}")
                return None
            
            # parts[0] is speaker (should match), parts[1] is text
            # We can relax speaker check or enforce it. Let's just warn for now.
            speaker_part = parts[0]
            text_part = self.separator.join(parts[1:]) # In case text itself contains separator (unlikely)

            # Optional: Check if speaker matches
            # orig_speaker = orig.get('speaker', '') or ''
            # if speaker_part != orig_speaker:
            #     print(f"⚠️ Speaker mismatch in line {i}: '{orig_speaker}' vs '{speaker_part}'")
            
            new_item['text'] = text_part
            new_chunk.append(new_item)
            
        return new_chunk

    def _validate_translation(self, original: List[Dict[str, Any]], translated: List[Dict[str, Any]]) -> bool:
        """
        Strict validation logic (V2.1 compatible).
        """
        # 1. Line Count Check (Already checked in reconstruction, but good to double check)
        if len(original) != len(translated):
            return False

        for i, (src, tgt) in enumerate(zip(original, translated)):
            # 2. Structure Check (Type preservation)
            if src.get("type") != tgt.get("type"):
                print(f"❌ Type mismatch at line {i}.")
                return False
            
            # 3. Control Characters Check
            if not self._validate_tags(src.get("text", ""), tgt.get("text", "")):
                 print(f"❌ Tag mismatch at line {i}.")
                 return False

        return True

    def _validate_tags(self, src_text: str, tgt_text: str) -> bool:
        """
        Checks if control characters and tags are preserved.
        """
        tags_to_check = [
            r"\\n", r"\\!", r"\\.", r"\\\|", r"\\^", 
            r"\\C\[\d+\]", r"\\V\[\d+\]", r"\\N\[\d+\]", 
            r"\\I\[\d+\]", r"\\G", r"\\\{", r"\\\}"
        ]

        for pattern in tags_to_check:
            src_count = len(re.findall(pattern, src_text))
            tgt_count = len(re.findall(pattern, tgt_text))
            
            if src_count != tgt_count:
                print(f"   Tag mismatch: {pattern}. Src: {src_count}, Tgt: {tgt_count}")
                return False
        
        return True

    async def process_file(self, input_file: str, output_file: str, batch_size: int = 20):
        print(f"Reading from {input_file}...")
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                lines = [json.loads(line) for line in f if line.strip()]
        except Exception as e:
            print(f"Failed to load input file: {e}")
            return

        total_lines = len(lines)
        print(f"Loaded {total_lines} lines from {input_file}")
        
        translated_results = []
        
        # Create batches
        batches = [lines[i:i + batch_size] for i in range(0, total_lines, batch_size)]
        
        for i, batch in enumerate(batches):
            print(f"Processing batch {i+1}/{len(batches)} ({len(batch)} lines)...")
            translated_batch = await self.translate_chunk(batch)
            if translated_batch:
                translated_results.extend(translated_batch)
            else:
                # Fallback: keep original if translation fails completely
                print(f"⚠️ Batch {i+1} failed completely. Keeping original.")
                translated_results.extend(batch)
            
            # Save progress periodically
            if (i + 1) % 5 == 0:
                self._save_results(output_file, translated_results)
                print(f"  -- Progress saved ({len(translated_results)}/{total_lines}) --")

        # Final Save
        self._save_results(output_file, translated_results)
        print(f"Translation complete. Saved {len(translated_results)} lines to {output_file}")

    def _save_results(self, output_file: str, results: List[Dict[str, Any]]):
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            for item in results:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

# --- Main Execution ---
async def main():
    parser = argparse.ArgumentParser(description="RPG Maker Translator")
    parser.add_argument("--input-file", type=str, help="Path to input JSONL file")
    parser.add_argument("--output-file", type=str, default="trans4/output/translated_texts.txt", help="Path to output file")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size for translation")
    args = parser.parse_args()

    translator = Translator()
    
    if args.input_file:
        await translator.process_file(args.input_file, args.output_file, args.batch_size)
    else:
        # Mock data for testing V2.1 Logic
        test_chunk = [
            {"page_id": "test_01", "speaker": "Hero", "text": "Hello, world!\\nThis is a test.", "type": "dialog"},
            {"page_id": "test_01", "speaker": "Villain", "text": "Die!\\!", "type": "dialog"},
            {"page_id": "test_01", "speaker": None, "text": "System message.", "type": "dialog"}
        ]
        
        print("Starting translation test (V2.1 Optimized)...")
        
        # Simulate the transformation manually to show what's happening
        optimized = []
        for item in test_chunk:
            speaker = item.get('speaker', '') or ''
            text = item.get('text', '')
            optimized.append(f"{speaker}{translator.separator}{text}")
        
        print(f"Optimized Prompt Payload:\n{json.dumps(optimized, indent=2, ensure_ascii=False)}")
        
        # NOTE: Actual API call will fail without keys, but logic flow is verified.
        # result = await translator.translate_chunk(test_chunk)
    
    await translator.close()

if __name__ == "__main__":
    asyncio.run(main())
