from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_settings, normalized_provider
from retrieval.llm import build_llm


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Loading settings from .env...")
    settings = load_settings()
    provider = normalized_provider(settings)

    print(f"Active LLM Provider : {provider}")
    print(f"Active LLM Model    : {settings.model_name}")
    if provider == "custom":
        print(f"Custom Base URL     : {settings.custom_llm_base_url}")

    print("\nBuilding LLM client...")
    llm = build_llm(settings=settings, temperature=0.1)
    print(" -> Client instantiated successfully!")

    print("\nTesting ping to LLM endpoint (sending simple message)...")
    try:
        response = llm.invoke("Hello! Please respond with exactly three words: 'LLM connection successful'.")
        print(f" -> LLM Response: {response.content}\n")
        print("[✓] Step 7 Verification Complete!")
    except Exception as exc:
        print(f" [!] Error communicating with endpoint: {exc}")
        if provider == "custom":
            try:
                from openai import OpenAI
                client = OpenAI(base_url=settings.custom_llm_base_url, api_key=settings.custom_llm_api_key)
                models = client.models.list()
                model_ids = [m.id for m in models.data]
                print(f"\n [i] Authorized models for your API key on {settings.custom_llm_base_url}:")
                for mid in model_ids:
                    print(f"   - {mid}")
                if model_ids:
                    print(f"\n --> Action Required: Update LLM_MODEL={model_ids[0]} in your .env file!")
            except Exception as e:
                print(f"\n [!] Failed to fetch model list from endpoint via OpenAI SDK: {e}")
                print(" --> Tip: Please double check if your CUSTOM_LLM_API_KEY is active and valid.")


if __name__ == "__main__":
    main()
