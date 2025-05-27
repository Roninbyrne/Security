from Security.core.bot import Anony
from Security.core.dir import dirr
from Security.core.git import git
from Security.misc import dbb, heroku

from .logging import LOGGER

dirr()
git()
dbb()
heroku()

app = Anony()
