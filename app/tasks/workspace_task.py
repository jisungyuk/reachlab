TASK_KEY          = 'workspace'
TASK_LABEL        = 'Workspace Task'
HAS_TARGETS       = False
HAS_SESSIONS      = True
HAS_GAME_SETTINGS = True

SESSIONS_SCREEN      = 'workspace_sessions'
GAME_SCREEN          = 'workspace_game'
GAME_SETTINGS_SCREEN = 'workspace_game_settings'


def build_screens(main_window, state):
    from tasks.workspace.sessions      import SessionScreen
    from tasks.workspace.game          import GameScreen
    from tasks.workspace.game_settings import GameSettingsScreen
    return {
        SESSIONS_SCREEN:      SessionScreen(state, main_window),
        GAME_SCREEN:          GameScreen(state, main_window.liberty, main_window),
        GAME_SETTINGS_SCREEN: GameSettingsScreen(state, main_window),
    }
