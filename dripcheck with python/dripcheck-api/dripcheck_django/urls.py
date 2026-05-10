from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('auth/', include('accounts.urls')),
    path('api/bundle-generate/', include('bundle_generate.urls')),
]
