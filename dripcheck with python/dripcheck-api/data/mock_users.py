from models.types import UserProfile

mock_users = [
    UserProfile(
        user_id='user_demo',
        username='Demo User',
        email='demo@dripcheck.io',
        skin_tone='Medium',
        hair_color='Black',
        body_type='Athletic',
        daily_routines=['Work', 'Gym'],
        occasion_frequency={'Casual': 'Daily', 'Business': 'Weekly'},
        style_vibes=['Minimalist', 'Classic'],
        favorite_colors=['White', 'Navy', 'Black'],
        avoided_colors=[],
        fit_preferences=['Slim', 'Regular'],
        material_sensitivity=[],
        pattern_preferences=['Solid'],
        onboarding_complete=True,
        created_at='2024-01-01T00:00:00Z'
    )
]
