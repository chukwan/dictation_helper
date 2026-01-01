import asyncio
import edge_tts

async def test_direct_edge():
    text = "Hello"
    voice = "en-US-AriaNeural"
    rates = ["+0%", "+10%", "-10%", None]
    
    for r in rates:
        print(f"Testing rate: {r}")
        try:
            # If r is None, don't pass rate
            if r is None:
                communicate = edge_tts.Communicate(text, voice)
            else:
                communicate = edge_tts.Communicate(text, voice, rate=r)
            
            data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    data += chunk["data"]
            print(f"Success! Bytes: {len(data)}")
        except Exception as e:
            print(f"Failed with rate {r}: {e}")

if __name__ == "__main__":
    asyncio.run(test_direct_edge())
