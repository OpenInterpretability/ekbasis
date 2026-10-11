import os
SECRET_KEY = "test-only"
INSTALLED_APPS = ["shop"]
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": os.environ["DB_HOST"],
                         "PORT": os.environ["DB_PORT"], "NAME": os.environ["DB_NAME"], "USER": os.environ["DB_USER"],
                         "PASSWORD": os.environ["DB_PASSWORD"]}}
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
