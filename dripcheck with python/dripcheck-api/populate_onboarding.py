import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dripcheck_django.settings')
django.setup()

from accounts.models import OnboardingQuestion, OnboardingOption

def populate():
    questions_data = [
        {
            "text": "What’s Your Fashion Style?",
            "type": "multiple_choice",
            "options": ["Casual", "Streetwear", "Formal", "Minimal", "Ethnic", "Sporty", "Vintage", "Korean Fashion", "Smart Casual"],
            "other_option": "Other (Type your own style)"
        },
        {
            "text": "What Clothes Do You Wear Most?",
            "type": "multiple_choice",
            "options": ["T-Shirts", "Shirts", "Hoodies", "Jeans", "Cargo Pants", "Shorts", "Sneakers", "Jackets", "Traditional Wear"],
            "other_option": "Add Custom Clothing Item"
        },
        {
            "text": "What Colors Do You Prefer Wearing?",
            "type": "multiple_choice",
            "options": ["Black", "White", "Blue", "Grey", "Beige", "Green", "Red", "Pastel Shades"],
            "other_option": "Choose Custom Color"
        },
        {
            "text": "What Do You Want DripCheck To Help You With?",
            "type": "multiple_choice",
            "options": ["Best Outfit Suggestions", "Matching Clothes From My Wardrobe", "Daily Outfit Planner", "Fashion Recommendations", "Color Combination Suggestions", "Occasion-Based Styling", "AI Fashion Rating"],
            "other_option": "Other (Write your goal)"
        },
        {
            "text": "How often do you buy clothes?",
            "type": "single_choice",
            "options": ["Monthly", "Every Few Months", "Occasionally", "Only During Sales"],
            "other_option": "Prefer Not To Say"
        }
    ]

    OnboardingQuestion.objects.all().delete()

    for idx, q_data in enumerate(questions_data):
        question = OnboardingQuestion.objects.create(
            text=q_data["text"],
            question_type=q_data["type"],
            order=idx + 1
        )
        
        for opt_text in q_data["options"]:
            OnboardingOption.objects.create(
                question=question,
                text=opt_text,
                is_other=False
            )
        
        if q_data.get("other_option"):
            OnboardingOption.objects.create(
                question=question,
                text=q_data["other_option"],
                is_other=True
            )
    
    print("Successfully populated onboarding questions and options.")

if __name__ == '__main__':
    populate()
