"""Who made this, and where the code is. Shown in About, `--source`, and left for anyone who opens the binaries."""
from . import brand

AUTHOR = brand.AUTHOR
SOURCE_URL = brand.SOURCE_URL
LICENSE = brand.LICENSE

MESSAGE = """
 ------------------------------------------------------------------------------
  Hello, curious reverse engineer!  \U0001F44B

  You put real effort into taking this program apart. Thank you, that is
  genuinely flattering. But you did not have to: %(name)s is OPEN SOURCE
  (%(license)s) and every single line you are staring at is public:

      %(url)s      (author: %(author)s)

  Readable, documented, with tests. A star on the repo is a lot cheaper
  than a disassembler.  \U0001F642

  سلام مهندس معکوس عزیز! لازم نبود زحمت بکشی؛ کد کامل و رایگان روی گیت‌هاب هست.
 ------------------------------------------------------------------------------
""" % {"name": brand.NAME, "license": brand.LICENSE, "url": brand.SOURCE_URL, "author": brand.AUTHOR}


def hello():
    """The message above; also what `--source` prints."""
    return MESSAGE
