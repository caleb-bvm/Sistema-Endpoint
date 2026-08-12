import os

from config.settings.development import *


DATABASES["default"]["NAME"] = os.environ["VISUAL_REVIEW_DB"]
