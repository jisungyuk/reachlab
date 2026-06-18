TASK_KEY          = 'workspace2'
TASK_LABEL        = 'Workspace Task 2'
HAS_TARGETS       = False
HAS_SESSIONS      = False
HAS_GAME_SETTINGS = True
HAS_DIGITIZATION  = False

GAME_SCREEN          = 'workspace2_game'
GAME_SETTINGS_SCREEN = 'workspace2_game_settings'


def build_screens(main_window, state):
    from tasks.workspace2.game          import GameScreen
    from tasks.workspace2.game_settings import GameSettingsScreen
    return {
        GAME_SCREEN:          GameScreen(state, main_window.liberty, main_window),
        GAME_SETTINGS_SCREEN: GameSettingsScreen(state, main_window),
    }
