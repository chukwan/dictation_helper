
import re

def split_into_sentences(text):
    sentences = re.split(r'(?<=[.?!,。？！，])\s*', text)
    return [s.strip() for s in sentences if s.strip()]

test_en = "Hello, world. This is a test, right?"
test_zh = "你好，世界。這是測試，對吧？"

print(f"EN: {split_into_sentences(test_en)}")
print(f"ZH: {split_into_sentences(test_zh)}")
