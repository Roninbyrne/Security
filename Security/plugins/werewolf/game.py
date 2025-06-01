from Security import app
from Security.plugins.werewolf import (
    werewolf_callbacks,
    werewolf_commands,
    werewolf_filters
)

if __name__ == "__main__":
    app.run()
