from Yumi.core.bot import Anony
from Yumi.core.dir import dirr
from Yumi.core.git import git
from Yumi.misc import dbb, heroku

from .logging import LOGGER

dirr()
git()
dbb()
heroku()

app = Anony()
