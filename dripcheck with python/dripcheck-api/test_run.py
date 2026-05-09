import asyncio
from services.data_service import get_bundles

async def main():
    print("Testing bundle generation...")
    bundles = await get_bundles("user_demo")
    print(f"Generated {len(bundles)} bundles for user_demo")
    for i, bundle in enumerate(bundles):
        print(f"\nBundle {i+1}: Score = {bundle.compatibility_score}")
        print(f"Tags: {bundle.style_tags}")
        print(f"Dominant Color: {bundle.dominant_color} ({bundle.dominant_palette})")

if __name__ == "__main__":
    asyncio.run(main())
